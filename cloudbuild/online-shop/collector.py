#!/usr/bin/env python3
"""Adopt only the policy-selected Collector. Application release #87 is unchanged."""
import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import tarfile
import tempfile
import urllib.error
import urllib.parse
import urllib.request

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location("catalog_release", HERE / "release.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)
require = r.require
SCRIPT = "cloudbuild/online-shop/collector.py"
TRUST_FILES = (*r.TRUSTED_FILES, SCRIPT, "cloudbuild/online-shop/collector-tools.json", "deploy/online-shop/policy.json")
ACCEPT = ", ".join(("application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
                    "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"))


def policy():
    document = r.read(ROOT / "deploy/online-shop/policy.json")
    require(type(document.get("version")) is int and document["version"] == 1, "invalid_support_policy_version")
    c = document["collector"]
    require(set(c) == {"version", "upstream_repository", "index_digest", "manifest_digest", "config_digest", "platform",
                       "mirror_image", "certificate_identity", "certificate_oidc_issuer"}, "invalid_collector_policy")
    require(c["upstream_repository"] == "ghcr.io/open-telemetry/opentelemetry-collector-releases/opentelemetry-collector-contrib"
            and c["platform"] == "linux/amd64" and re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", c["version"]), "unsupported_collector")
    require(all(re.fullmatch(r.DIGEST, c[k]) for k in ("index_digest", "manifest_digest", "config_digest")), "invalid_collector_digest")
    require(c["mirror_image"] == r.policy()["registry"] + "/otelcol-contrib@" + c["manifest_digest"], "unapproved_collector_mirror")
    require(c["certificate_identity"] == "https://github.com/open-telemetry/opentelemetry-collector-releases/.github/workflows/base-release.yaml@refs/tags/v" + c["version"]
            and c["certificate_oidc_issuer"] == "https://token.actions.githubusercontent.com", "unapproved_collector_publisher")
    return c


def reviewed(revision):
    require(re.fullmatch(r.SHA, revision or ""), "configuration_revision_required")
    with r.fetched(r.SDP, revision) as source:
        source.git("fetch", "--no-tags", r.SDP + ".git", "main")
        source.git("merge-base", "--is-ancestor", revision, "FETCH_HEAD")
        for name in TRUST_FILES:
            require((ROOT / name).read_bytes().replace(b"\r\n", b"\n") == source.blob(name), "unreviewed_collector_files")


def tool(name):
    """Private cache, exact release checksums; never execute an ambient PATH tool."""
    system = platform.system().lower()
    require(system in ("windows", "linux") and platform.machine().lower() in ("amd64", "x86_64"), "unsupported_tool_platform")
    lock = r.read(HERE / "collector-tools.json")[name]
    asset = lock[system]
    directory = ROOT / ".local-validation/collector-tools" / name / lock["version"] / system
    directory.mkdir(parents=True, exist_ok=True)
    archive = directory / asset["asset"]
    if not archive.exists():
        url = "https://github.com/" + lock["repository"] + "/releases/download/" + lock["version"] + "/" + asset["asset"]
        with urllib.request.urlopen(url, timeout=120) as response:
            data = response.read()
        require(r.sha(data) == asset["sha256"], "tool_download_hash_mismatch")
        archive.write_bytes(data)
    data = archive.read_bytes()
    require(r.sha(data) == asset["sha256"], "tool_cache_hash_mismatch")
    if "member" in asset:
        with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as compressed:
            member = compressed.getmember(asset["member"])
            require(member.isfile(), "invalid_tool_archive_member")
            executable_bytes = compressed.extractfile(member).read()
        executable = directory / asset["member"]
        if executable.exists():
            require(executable.read_bytes() == executable_bytes, "tool_executable_hash_mismatch")
        else:
            executable.write_bytes(executable_bytes)
    else:
        executable = archive
    executable.chmod(0o700)
    return str(executable)


def run(args, *, env=None, input=None):
    result = subprocess.run(args, input=input, capture_output=True, env=env, timeout=600)
    require(result.returncode == 0, "collector_tool_failed")
    return result.stdout


def clean_env():
    return {k: v for k, v in os.environ.items() if not k.startswith(("COSIGN_", "SIGSTORE_", "TUF_", "REKOR_", "FULCIO_"))}


def cosign(c):
    with tempfile.TemporaryDirectory(prefix="sdp-collector-cosign-") as directory:
        env = clean_env()
        env["DOCKER_CONFIG"] = directory
        result = r.decode(run([tool("cosign"), "verify", "--certificate-identity=" + c["certificate_identity"],
            "--certificate-oidc-issuer=" + c["certificate_oidc_issuer"], c["upstream_repository"] + "@" + c["index_digest"]], env=env))
    require(type(result) is list and result and all(
        item.get("critical", {}).get("image", {}).get("docker-manifest-digest") == c["index_digest"] for item in result),
        "collector_publisher_signature_mismatch")


class UpstreamRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        require("/blobs/" in req.full_url and target.scheme == "https"
                and target.hostname == "pkg-containers.githubusercontent.com", "unexpected_collector_redirect")
        # A public signed CDN URL never receives the GHCR token or cloud auth.
        return urllib.request.Request(newurl)


class Upstream:
    def __init__(self, c):
        self.path = c["upstream_repository"].removeprefix("ghcr.io/")
        self.opener = urllib.request.build_opener(UpstreamRedirect())
        token_url = "https://ghcr.io/token?" + urllib.parse.urlencode({"scope": "repository:" + self.path + ":pull"})
        with self.opener.open(token_url, timeout=60) as response:
            self.token = r.decode(response.read())["token"]

    def get(self, kind, digest):
        require(kind in ("manifests", "blobs") and re.fullmatch(r.DIGEST, digest), "invalid_upstream_reference")
        request = urllib.request.Request("https://ghcr.io/v2/" + self.path + "/" + kind + "/" + digest,
            headers={"Authorization": "Bearer " + self.token, "Accept": ACCEPT})
        with self.opener.open(request, timeout=120) as response:
            return response.read()


class MirrorBlobRedirect(urllib.request.HTTPRedirectHandler):
    """One observed AR blob -> scoped download hop, confined to its HTTPS origin."""
    def __init__(self, repository, digest):
        super().__init__()
        p = r.policy()
        require(repository == p["registry"] + "/otelcol-contrib" and re.fullmatch(r.DIGEST, digest),
                "unapproved_collector_blob")
        host, path = repository.split("/", 1)
        self.host = host
        self.start = "https://" + host + "/v2/" + path + "/blobs/" + digest
        self.download_path = (r"/artifacts-downloads/namespaces/" + re.escape(p["project"])
                              + r"/repositories/secure-delivery/downloads/[A-Za-z0-9_-]{16}")

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # urllib resolves relative Location values before invoking this callback;
        # explicit urljoin also makes direct callers follow the same rule.
        target_url = urllib.parse.urljoin(req.full_url, newurl)
        target = urllib.parse.urlsplit(target_url)
        location = headers.get("Location", newurl)
        original = urllib.parse.urlsplit(location)
        require(code == 302 and req.get_method() == "GET" and req.full_url == self.start
                and not any(ord(char) <= 32 or ord(char) == 127 for char in location + newurl)
                and not any(char in location for char in ("?", "#", "\\"))
                and original.scheme in ("", "https") and original.netloc == (self.host if original.scheme else "")
                and re.fullmatch(self.download_path, original.path)
                and target_url == urllib.parse.urljoin(req.full_url, location)
                and target.scheme == "https" and target.netloc == self.host
                and not target.query and not target.fragment
                and re.fullmatch(self.download_path, target.path), "unexpected_collector_blob_redirect")
        auth = req.get_header("Authorization")
        require(isinstance(auth, str) and auth.startswith("Basic "), "collector_blob_credentials_required")
        # Only this same-origin, repository-scoped GET retains registry auth.
        # No Cookie, Proxy-Authorization, Host or other ambient headers propagate.
        return urllib.request.Request(target_url, headers={"Authorization": auth,
            "Accept": req.get_header("Accept", "*/*")})


def blob_bytes(cloud, repository, digest):
    redirect = MirrorBlobRedirect(repository, digest)
    require(isinstance(cloud.token, str) and bool(cloud.token), "collector_blob_credentials_required")
    auth = "Basic " + base64.b64encode(("oauth2accesstoken:" + cloud.token).encode()).decode()
    request = urllib.request.Request(redirect.start, headers={"Authorization": auth, "Accept": ACCEPT})
    with urllib.request.build_opener(redirect).open(request, timeout=120) as response:
        return response.read()


class Mirror:
    def __init__(self, c, cloud):
        repository = c["mirror_image"].split("@")[0]
        host, path = repository.split("/", 1)
        self.repository = repository
        self.base, self.cloud = "https://" + host + "/v2/" + path, cloud

    def get(self, kind, digest):
        require(kind in ("manifests", "blobs") and re.fullmatch(r.DIGEST, digest), "invalid_mirror_reference")
        if kind == "blobs":
            return blob_bytes(self.cloud, self.repository, digest)
        return self.cloud.request(self.base + "/" + kind + "/" + digest, registry=True)


def descriptor(value):
    require(type(value) is dict and re.fullmatch(r.DIGEST, value.get("digest", ""))
            and type(value.get("size")) is int and value["size"] > 0 and not value.get("urls"), "invalid_collector_descriptor")


def content(reader, c, raw=None):
    raw = reader.get("manifests", c["manifest_digest"]) if raw is None else raw
    require("sha256:" + r.sha(raw) == c["manifest_digest"], "collector_manifest_hash")
    manifest = r.decode(raw)
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2 and "manifests" not in manifest,
            "collector_single_manifest_required")
    descriptor(manifest["config"])
    require(manifest["config"]["digest"] == c["config_digest"], "collector_config_binding")
    config = reader.get("blobs", c["config_digest"])
    require("sha256:" + r.sha(config) == c["config_digest"] and len(config) == manifest["config"]["size"], "collector_config_hash")
    image = r.decode(config)
    require(image.get("os") == "linux" and image.get("architecture") == "amd64", "collector_platform")
    layers = manifest.get("layers")
    require(type(layers) is list and layers and len(layers) <= 32, "invalid_collector_layers")
    for layer in layers:
        descriptor(layer)
        data = reader.get("blobs", layer["digest"])
        require("sha256:" + r.sha(data) == layer["digest"] and len(data) == layer["size"], "collector_layer_hash")
    return raw


def publisher(c):
    cosign(c)
    reader = Upstream(c)
    raw = reader.get("manifests", c["index_digest"])
    require("sha256:" + r.sha(raw) == c["index_digest"], "collector_index_hash")
    index = r.decode(raw)
    require(type(index.get("schemaVersion")) is int and index["schemaVersion"] == 2, "invalid_collector_index")
    members = [m for m in index["manifests"] if m.get("platform", {}).get("os") == "linux" and m.get("platform", {}).get("architecture") == "amd64"]
    require(len(members) == 1 and members[0].get("digest") == c["manifest_digest"], "collector_signed_platform_membership")
    descriptor(members[0])
    manifest = content(reader, c)
    require(len(manifest) == members[0]["size"], "collector_index_member_size")
    return {"status": "publisher_verified", "index_digest": c["index_digest"], "manifest_digest": c["manifest_digest"],
            "config_digest": c["config_digest"], "platform": c["platform"], "layer_bytes_verified": True,
            "certificate_identity": c["certificate_identity"], "certificate_oidc_issuer": c["certificate_oidc_issuer"]}


def verify(c, cloud):
    proof = publisher(c)
    content(Mirror(c, cloud), c)
    return {**proof, "status": "mirror_verified", "artifact": c["mirror_image"]}


def copy(c, cloud):
    """One exact manifest, no index/tags/rebuild; auth only for approved destination."""
    with tempfile.TemporaryDirectory(prefix="sdp-collector-copy-") as directory:
        env = clean_env()
        env["DOCKER_CONFIG"] = directory
        executable = tool("crane")
        run([executable, "auth", "login", c["mirror_image"].split("/")[0], "-u", "oauth2accesstoken", "--password-stdin"],
            env=env, input=(cloud.token + "\n").encode())
        run([executable, "copy", "--jobs=1", c["upstream_repository"] + "@" + c["manifest_digest"], c["mirror_image"]], env=env)


def mirror(c, cloud):
    proof = publisher(c)
    reader = Mirror(c, cloud)
    try:
        raw = reader.get("manifests", c["manifest_digest"])
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    else:
        content(reader, c, raw)
        return {**proof, "status": "mirror_already_present", "artifact": c["mirror_image"]}
    try:
        copy(c, cloud)
    except (OSError, ValueError, subprocess.SubprocessError):
        # Read back an uncertain write once; never blindly retry the copy.
        content(reader, c)
        return {**proof, "status": "mirror_recovered", "artifact": c["mirror_image"]}
    content(reader, c)
    return {**proof, "status": "mirrored", "artifact": c["mirror_image"]}


def authority():
    p = r.policy()
    prefix = "projects/" + p["project"]
    key = prefix + "/locations/us-central1/keyRings/secure-delivery-attestation/cryptoKeys/verification/cryptoKeyVersions/1"
    return prefix + "/attestors/secure-delivery-verification", prefix + "/notes/secure-delivery-verification", key, "//cloudkms.googleapis.com/v1/" + key


def occurrence(c, cloud, helper, name):
    require(re.fullmatch("projects/" + re.escape(r.policy()["project"]) + r"/occurrences/[A-Za-z0-9_-]+", name or ""), "invalid_collector_occurrence")
    attestor, note, key, public = authority()
    observed = r.decode(cloud.request("https://containeranalysis.googleapis.com/v1/" + name))
    require(helper.inspect_occurrence([observed], c["mirror_image"], public, note) == name, "collector_occurrence_mismatch")
    helper.validate_signature(observed, attestor, cloud.token)
    return name


def existing(c, cloud, helper):
    token, seen, matches = "", set(), []
    for _ in range(10):
        query = urllib.parse.urlencode({"filter": 'kind="ATTESTATION"', "pageSize": 100, "pageToken": token})
        value = r.decode(cloud.request("https://containeranalysis.googleapis.com/v1/projects/" + r.policy()["project"] + "/occurrences?" + query))
        for item in value.get("occurrences", []):
            if item.get("resourceUri", "").removeprefix("https://") == c["mirror_image"] and item.get("noteName") == authority()[1]:
                matches.append(occurrence(c, cloud, helper, item.get("name")))
        token = value.get("nextPageToken", "")
        if not token:
            return sorted(set(matches))
        require(token not in seen, "occurrence_pagination_cycle")
        seen.add(token)
    raise ValueError("occurrence_listing_incomplete")


def signer_identity():
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args):
            raise ValueError("unexpected_metadata_redirect")
    request = urllib.request.Request("http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email",
                                     headers={"Metadata-Flavor": "Google"})
    with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
        email = response.read().decode().strip()
    require("projects/" + r.policy()["project"] + "/serviceAccounts/" + email == r.policy()["signer"], "collector_signer_identity_mismatch")


def attest(c, cloud, helper, *, inspect=False):
    if not inspect:
        signer_identity()
    proof = verify(c, cloud)  # No supplied verification result is accepted.
    matches = existing(c, cloud, helper)
    if matches:
        reference, action = matches[0], "reused"
    else:
        require(not inspect, "collector_attestation_missing")
        attestor, note, key, public = authority()
        try:
            created = helper.sign_and_create(c["mirror_image"], r.policy()["project"], attestor, note, key, public, cloud.token)
        except (OSError, ValueError, subprocess.SubprocessError):
            # A failed response may follow successful occurrence creation.
            matches = existing(c, cloud, helper)
            require(bool(matches), "collector_signing_uncertain_inspect_before_retry")
            reference, action = matches[0], "recovered"
        else:
            reference = occurrence(c, cloud, helper, created.get("name"))
            action = "created"
    return {**proof, "status": "trusted", "kind": "supporting_image", "occurrence": reference,
            "signature_verified": True, "attestation_action": action, "verified_at": datetime.now(timezone.utc).isoformat()}


def signing_request(revision):
    require(re.fullmatch(r.SHA, revision or ""), "configuration_revision_required")
    return {"source": {"gitSource": {"url": r.SDP + ".git", "revision": revision}}, "serviceAccount": r.policy()["signer"],
            "timeout": "900s", "options": {"logging": "CLOUD_LOGGING_ONLY"},
            "tags": ["collector-support-v1", revision],
            "steps": [{"id": "verify-collector-publisher-content-mirror-and-attest", "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim",
                       "entrypoint": "bash", "dir": "/workspace", "args": ["-ceu", "apt-get update -qq && apt-get install -y -qq git >/dev/null\n"
                       "python3 " + SCRIPT + " attest --configuration-revision " + revision]}]}


def signing_builds(cloud, revision):
    """Caller-only recovery lookup; signer does not acquire builds.list permission."""
    base = "https://cloudbuild.googleapis.com/v1/projects/" + r.policy()["project"] + "/locations/us-central1/builds"
    token, seen, found = "", set(), []
    for _ in range(10):
        query = urllib.parse.urlencode({"filter": 'tags="collector-support-v1" AND tags="' + revision + '"', "pageSize": 100, "pageToken": token})
        value = r.decode(cloud.request(base + "?" + query))
        for build in value.get("builds", []):
            expected = signing_request(revision)
            steps = [{k:v for k,v in step.items() if k not in ("status","exitCode","timing","pullTiming")} for step in build.get("steps",[])]
            require(build.get("source") == expected["source"] and build.get("serviceAccount") == expected["serviceAccount"]
                    and steps == expected["steps"] and build.get("timeout") == expected["timeout"]
                    and build.get("options") in (expected["options"], {**expected["options"], "pool": {}, "workerRelease": "legacy"})
                    and not any(build.get(k) for k in ("images","artifacts","substitutions","secrets","availableSecrets","dependencies","gitConfig")),
                    "unexpected_existing_collector_signing_build")
            found.append({"id":build["id"], "status":build["status"]})
        token = value.get("nextPageToken", "")
        if not token:
            return found
        require(token not in seen, "build_pagination_cycle")
        seen.add(token)
    raise ValueError("build_listing_incomplete")


def submit_signing(cloud, revision):
    found = signing_builds(cloud, revision)
    if found:
        return {"status":"existing_signing_builds", "builds":found, "resubmitted":False}
    base = "https://cloudbuild.googleapis.com/v1/projects/" + r.policy()["project"] + "/locations/us-central1/builds"
    try:
        operation = r.decode(cloud.request(base, signing_request(revision)))
    except (OSError, ValueError):
        found = signing_builds(cloud, revision)
        require(bool(found), "collector_submission_uncertain_do_not_resubmit")
        return {"status":"recovered_signing_builds", "builds":found, "resubmitted":False}
    return {"status":"signing_submitted", "operation":operation, "resubmitted":False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("publisher", "verify", "mirror", "inspect", "attest", "signing-request", "submit-signing"))
    parser.add_argument("--configuration-revision")
    args = parser.parse_args()
    try:
        c = policy()
        if args.action == "publisher":
            result = publisher(c)
        else:
            reviewed(args.configuration_revision)
            cloud = r.Cloud()
            if args.action in ("inspect", "attest"):
                result = attest(c, cloud, r.attestation_helper(), inspect=args.action == "inspect")
            elif args.action == "mirror":
                result = mirror(c, cloud)
            elif args.action == "verify":
                result = verify(c, cloud)
            else:
                verify(c, cloud)
                result = signing_request(args.configuration_revision) if args.action == "signing-request" else submit_signing(cloud, args.configuration_revision)
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        # Do not print tool stderr, tokens, signed CDN URLs or API responses.
        reason = str(error) if type(error) is ValueError else type(error).__name__
        print(json.dumps({"status":"failed", "reason":reason}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
