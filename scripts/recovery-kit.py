"""Read-only registry export and offline recovery-kit verification.

No registry writes, Terraform execution, credential storage or cloud mutations.
The inventory is a JSON list of immutable Artifact Registry image references.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urljoin, urlsplit

DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
IMAGE = re.compile(r"([a-z0-9-]+-docker\.pkg\.dev)/([a-z0-9-]+/[^@\s]+)@(sha256:[0-9a-f]{64})\Z")
MANIFESTS = {
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
}


def digest_file(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return "sha256:" + h.hexdigest()


def local_path(root, relative):
    p = PurePosixPath(relative)
    if not relative or p.is_absolute() or ".." in p.parts or "\\" in relative or ":" in relative:
        raise ValueError("unsafe kit path")
    target = root.joinpath(*p.parts)
    if target.resolve() != root.resolve().joinpath(*p.parts):
        raise ValueError("redirected kit path")
    return target


def blob_path(root, digest):
    if not DIGEST.fullmatch(digest):
        raise ValueError("only sha256 content digests are supported")
    return root / "blobs" / "sha256" / digest.split(":")[1]


def children(manifest):
    if manifest.get("schemaVersion") != 2 or manifest.get("mediaType") not in MANIFESTS:
        raise ValueError("unsupported manifest format")
    if manifest.get("subject"):
        raise ValueError("subject/referrer artifacts require explicit inventory review")
    if "manifests" in manifest:
        if any(d.get("mediaType") not in MANIFESTS for d in manifest["manifests"]):
            raise ValueError("index child must be a supported manifest")
        return manifest["manifests"]
    return [manifest["config"], *manifest["layers"]]


def export_images(images, root, fetch):
    """fetch(image, kind, digest) returns a streaming context manager.

    Keep original manifest bytes: reserialization changes signed image digests.
    Recursively retain every platform, config and layer; share identical blobs.
    """
    root = Path(root)
    if root.is_symlink():
        raise ValueError("redirected OCI root")
    (root / "blobs/sha256").mkdir(parents=True, exist_ok=True)
    descriptors = []

    def copy(image, digest, kind, expected_size=None):
        path = blob_path(root, digest)
        if path.resolve() != root.resolve() / "blobs/sha256" / digest.split(":")[1]:
            raise ValueError("redirected blob")
        if not path.exists():
            temporary = path.with_suffix(".partial")
            with fetch(image, kind, digest) as response, temporary.open("xb") as out:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        out.write(chunk)
            if digest_file(temporary) != digest:
                raise ValueError("download digest mismatch")
            temporary.replace(path)
        if digest_file(path) != digest or (expected_size is not None and path.stat().st_size != expected_size):
            raise ValueError("blob digest/size mismatch")
        if kind == "manifests":
            value = json.loads(path.read_bytes())
            for desc in children(value):
                if desc.get("urls"):
                    raise ValueError("external/foreign layers require explicit review")
                copy(image, desc["digest"], "manifests" if desc["mediaType"] in MANIFESTS else "blobs", desc["size"])
            return value

    for image in sorted(set(images)):
        match = IMAGE.fullmatch(image)
        if not match:
            raise ValueError("require immutable Artifact Registry reference")
        digest = match[3]
        value = copy(image, digest, "manifests")
        descriptors.append({"mediaType": value["mediaType"], "digest": digest,
                            "size": blob_path(root, digest).stat().st_size,
                            "annotations": {"org.opencontainers.image.ref.name": image}})
    (root / "oci-layout").write_text('{"imageLayoutVersion":"1.0.0"}\n', encoding="utf-8")
    (root / "index.json").write_text(json.dumps({"schemaVersion": 2, "manifests": descriptors}, indent=2) + "\n", encoding="utf-8")
    return verify_oci(root)


def verify_oci(root):
    root = Path(root)
    if json.loads((root / "oci-layout").read_text(encoding="utf-8"))["imageLayoutVersion"] != "1.0.0":
        raise ValueError("unsupported OCI layout")
    visited = set()

    def visit(desc):
        path = blob_path(root, desc["digest"])
        if path.resolve() != root.resolve() / "blobs/sha256" / desc["digest"].split(":")[1]:
            raise ValueError("redirected blob")
        if desc["digest"] in visited:
            if path.stat().st_size != desc["size"]:
                raise ValueError("conflicting descriptor size")
            return
        if path.stat().st_size != desc["size"] or digest_file(path) != desc["digest"]:
            raise ValueError("missing/corrupt blob")
        visited.add(desc["digest"])
        if desc["mediaType"] in MANIFESTS:
            for child in children(json.loads(path.read_bytes())):
                if child.get("urls"):
                    raise ValueError("external layer is not self-contained")
                visit(child)

    index = json.loads((root / "index.json").read_text(encoding="utf-8"))
    if index.get("schemaVersion") != 2 or not index.get("manifests"):
        raise ValueError("empty or invalid image index")
    names = []
    for desc in index["manifests"]:
        name = desc.get("annotations", {}).get("org.opencontainers.image.ref.name", "")
        match = IMAGE.fullmatch(name)
        if not match or match[3] != desc["digest"] or name in names:
            raise ValueError("invalid/duplicate image binding")
        names.append(name)
        visit(desc)
    return {"images": len(names), "blobs": len(visited), "references": names}


def verify_kit(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "kit-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != 1 or not manifest.get("files"):
        raise ValueError("invalid kit manifest")
    expected = set(manifest["files"])
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    if actual != expected | {"kit-manifest.json"}:
        raise ValueError("missing or unlisted kit files")
    for relative, row in manifest["files"].items():
        path = local_path(root, relative)
        if path.stat().st_size != row["size"] or digest_file(path) != row["digest"]:
            raise ValueError("kit file digest/size mismatch: " + relative)
    result = verify_oci(root / "images")
    if set(result["references"]) != set(manifest["required_images"]):
        raise ValueError("image inventory coverage mismatch")
    return {"files": len(expected), "images": result["images"], "blobs": result["blobs"]}


class Registry:
    def __init__(self, token):
        import requests
        self.session = requests.Session()
        self.token = token

    def __call__(self, image, kind, digest):
        match = IMAGE.fullmatch(image)
        if not match or kind not in {"manifests", "blobs"} or not DIGEST.fullmatch(digest):
            raise ValueError("invalid registry request")
        host, repository = match[1], match[2]
        response = self.session.get(f"https://{host}/v2/{repository}/{kind}/{digest}",
                                    auth=("oauth2accesstoken", self.token),
                                    headers={"Accept": ", ".join(sorted(MANIFESTS))},
                                    stream=True, allow_redirects=False, timeout=120)
        if response.status_code in (301, 302, 307, 308):
            target = urlsplit(urljoin(response.url, response.headers.get("Location", "")))
            project, repo = repository.split("/")[:2]
            allowed = rf"/artifacts-downloads/namespaces/{re.escape(project)}/repositories/{re.escape(repo)}/downloads/[A-Za-z0-9_-]{{16}}"
            if kind != "blobs" or target.scheme != "https" or target.netloc != host or target.query or target.fragment or not re.fullmatch(allowed, target.path):
                response.close()
                raise ValueError("unexpected registry redirect")
            response.close()
            response = self.session.get(target.geturl(), auth=("oauth2accesstoken", self.token),
                                        stream=True, allow_redirects=False, timeout=120)
        if response.status_code != 200:
            status = response.status_code
            response.close()
            raise ValueError("registry HTTP " + str(status))
        return response


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    v = sub.add_parser("verify")
    v.add_argument("kit", type=Path)
    e = sub.add_parser("export-images")
    e.add_argument("--inventory", required=True, type=Path)
    e.add_argument("--output", required=True, type=Path)
    e.add_argument("--token-stdin", required=True, action="store_true")
    args = parser.parse_args()
    if args.action == "verify":
        print(json.dumps(verify_kit(args.kit)))
    else:
        token = sys.stdin.readline().strip()
        if not token:
            raise SystemExit("registry access token required on stdin; never persist it")
        result = export_images(json.loads(args.inventory.read_text(encoding="utf-8")), args.output, Registry(token))
        print(json.dumps({k: result[k] for k in ("images", "blobs")}))
