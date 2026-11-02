#!/usr/bin/env python3
"""Read-only official Redis -> canonical Docker Hub -> approved registry proof."""
import argparse
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.request

HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result


r = module("redis_release", HERE / "release.py")
support = module("redis_tools", HERE / "collector.py")
require = r.require
POLICY_SHA = "8ad0587ef4fdd1298be088440f25a229edf15f5ce87caabf2de79335bdaf1925"


def policy():
    raw = (HERE / "redis-policy-v2.json").read_bytes().replace(b"\r\n", b"\n")
    require(r.sha(raw) == POLICY_SHA, "unreviewed_redis_policy")
    q = r.decode(raw)
    require(type(q.get("version")) is int and q["version"] == 2
            and q["upstream_repository"] == "docker.io/library/redis"
            and q["selection_repository"] == "docker.io/dmitryzhuravlev/online-shop-redis-cart"
            and q["platform"] == "linux/amd64"
            and q["admission_decision"] == "requires_verified_official_canonical_registry_chain", "unsupported_redis_policy")
    return q


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("unexpected_redis_source_redirect")


def source_bytes(repository, revision, path):
    require(repository in ("https://github.com/redis/docker-library-redis", "https://github.com/docker-library/official-images")
            and re.fullmatch(r.SHA, revision) and path in ("library/redis", "alpine/Dockerfile", "alpine/docker-entrypoint.sh"), "unapproved_redis_source_url")
    url = repository.replace("https://github.com/", "https://raw.githubusercontent.com/") + "/" + revision + "/" + path
    with urllib.request.build_opener(NoRedirect()).open(url, timeout=30) as response:
        return response.read()


@contextmanager
def reader(repository, q, cloud=None):
    approved = r.policy()["registry"] + q["intended_mirror_suffix"]
    require(repository in (q["upstream_repository"], q["selection_repository"], approved), "unapproved_redis_repository")
    with tempfile.TemporaryDirectory(prefix="sdp-redis-read-") as directory:
        env = support.clean_env(); env["DOCKER_CONFIG"] = directory
        executable = support.tool("crane")
        if repository == approved:
            require(cloud is not None, "redis_registry_credentials_required")
            support.run([executable, "auth", "login", repository.split("/")[0], "-u", "oauth2accesstoken", "--password-stdin"],
                        env=env, input=(cloud.token + "\n").encode())

        class Reader:
            def get(self, kind, digest):
                require(kind in ("manifests", "blobs") and re.fullmatch(r.DIGEST, digest), "invalid_redis_reference")
                return support.run([executable, "manifest" if kind == "manifests" else "blob", repository + "@" + digest], env=env)
        yield Reader()


def blob(read, descriptor, kind="blobs"):
    support.descriptor(descriptor)
    raw = read.get(kind, descriptor["digest"])
    require("sha256:" + r.sha(raw) == descriptor["digest"] and len(raw) == descriptor["size"], "redis_blob_hash_or_size")
    return raw


def content(read, q):
    raw = read.get("manifests", q["manifest_digest"])
    require("sha256:" + r.sha(raw) == q["manifest_digest"], "redis_manifest_hash")
    manifest = r.decode(raw)
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2 and "manifests" not in manifest, "redis_single_platform_required")
    require(manifest["config"]["digest"] == q["config_digest"], "redis_config_binding")
    config = r.decode(blob(read, manifest["config"]))
    require(config.get("os") == "linux" and config.get("architecture") == "amd64", "redis_platform")
    settings = config.get("config", {})
    require(settings.get("WorkingDir") == "/data" and settings.get("Cmd") == ["redis-server"]
            and settings.get("Entrypoint") == ["docker-entrypoint.sh"]
            and [x for x in settings.get("Env", []) if x.startswith("REDIS_VERSION=")] == ["REDIS_VERSION=" + q["redis_version"]], "redis_runtime_config")
    layers = manifest.get("layers")
    require(type(layers) is list and 0 < len(layers) <= 32, "invalid_redis_layers")
    for layer in layers: blob(read, layer)
    return {"manifest_digest": q["manifest_digest"], "config_digest": q["config_digest"], "layers_verified": len(layers)}


def official_source(q, read, fetch=source_bytes):
    meta = q["source_proof"]["official_images"]; source = q["producing_source"]
    raw = fetch(meta["repository"], meta["revision"], meta["path"])
    require("sha256:" + r.sha(raw) == meta["sha256"], "redis_official_metadata_hash")
    text = raw.decode("utf-8")
    require("GitRepo: " + source["repository"] + ".git\n" in text, "redis_official_repository")
    entries = [entry for entry in text.split("\n\n") if any(line.startswith("Tags: ") and q["discovery_selector"] in line[6:].split(", ") for line in entry.splitlines())]
    require(len(entries) == 1 and "GitCommit: " + source["revision"] in entries[0].splitlines()
            and "Directory: " + source["directory"] in entries[0].splitlines(), "redis_official_source_binding")
    arches = next((line.removeprefix("Architectures: ").split(", ") for line in entries[0].splitlines() if line.startswith("Architectures: ")), [])
    require("amd64" in arches, "redis_official_platform_missing")
    for path, digest in source["filesSha256"].items():
        data = fetch(source["repository"], source["revision"], path)
        require("sha256:" + r.sha(data) == digest, "redis_source_file_hash")

    index_raw = read.get("manifests", q["index_digest"])
    require("sha256:" + r.sha(index_raw) == q["index_digest"], "redis_index_hash")
    index = r.decode(index_raw)
    require(type(index.get("schemaVersion")) is int and index["schemaVersion"] == 2, "redis_index_schema")
    platforms = [d for d in index["manifests"] if d.get("platform", {}).get("os") == "linux"
                 and d["platform"].get("architecture") == "amd64" and not d["platform"].get("variant")]
    require(len(platforms) == 1 and platforms[0]["digest"] == q["manifest_digest"], "redis_index_platform_membership")
    blob(read, platforms[0], "manifests")
    expected = q["source_proof"]["attestation_manifest"]
    attested = [d for d in index["manifests"] if d.get("annotations", {}).get("vnd.docker.reference.digest") == q["manifest_digest"]
                and d["annotations"].get("vnd.docker.reference.type") == "attestation-manifest"]
    require(attested == [expected], "redis_index_provenance_membership")
    attestation = r.decode(blob(read, expected, "manifests"))
    statement = q["source_proof"]["statement"]
    require([d for d in attestation["layers"] if d.get("annotations", {}).get("in-toto.io/predicate-type") == "https://slsa.dev/provenance/v0.2"] == [statement], "redis_provenance_descriptor")
    document = r.decode(blob(read, statement))
    subjects = document.get("subject", [])
    require(document.get("_type") == "https://in-toto.io/Statement/v0.1" and document.get("predicateType") == "https://slsa.dev/provenance/v0.2"
            and subjects and all(x.get("digest") == {"sha256": q["manifest_digest"][7:]} for x in subjects)
            and any(x.get("name") == "pkg:docker/redis@" + q["discovery_selector"] + "?platform=linux%2Famd64" for x in subjects), "redis_provenance_subject")
    build = q["producing_build"]; predicate = document["predicate"]
    uri = source["repository"] + ".git#" + source["revision"]
    require(predicate.get("builder", {}).get("id") == build["builder_id"] and predicate.get("buildType") == build["build_type"]
            and predicate.get("metadata", {}).get("buildInvocationID") == build["id"]
            and predicate.get("invocation", {}).get("configSource") == {"uri": uri + ":" + source["directory"], "entryPoint": "Dockerfile"}
            and predicate["invocation"].get("environment", {}).get("platform") == q["platform"]
            and any(x.get("uri") == uri and x.get("digest") == {"sha1": source["revision"]} for x in predicate.get("materials", [])), "redis_provenance_source_build")
    return {"source_association": "verified", "publisher_signature_verified": False,
            "trust_basis": q["source_proof"]["trust_basis"], "index_digest": q["index_digest"], "build_invocation": build["id"]}


def upstream(q):
    with reader(q["upstream_repository"], q) as read:
        proof = official_source(q, read)
        result = content(read, q)
    return {**proof, **result, "status": "official_source_content_verified", "platform": q["platform"]}


def contracts(q):
    selected = q["selection_source"]
    with r.fetched(selected["repository"], selected["revision"]) as source:
        source.git("fetch", "--no-tags", selected["repository"] + ".git", "main")
        source.git("merge-base", "--is-ancestor", selected["revision"], "FETCH_HEAD")
        for path, digest in q["selection_contracts_sha256"].items():
            require("sha256:" + r.sha(source.blob(selected["workload_path"] + "/" + path)) == digest, "redis_aml_contract_hash")
        mapping = r.decode(source.blob(selected["workload_path"] + "/images.lock.json"))
        runtime = r.decode(source.blob(selected["workload_path"] + "/redis.runtime.json"))
        image = next(x["image"] for x in mapping["components"] if x["id"] == "redis-cart")
        require(image == {"repository": q["selection_repository"], "digest": q["manifest_digest"], "kind": "manifest", "platforms": [q["platform"]]}
                and runtime["configDigest"] == q["config_digest"] and runtime["redisVersion"] == q["redis_version"], "redis_aml_selection_mismatch")


def verify_chain(q, cloud):
    contracts(q)  # Unmerged dependency contract is never execution approval.
    proof = upstream(q)
    for repository in (q["selection_repository"], r.policy()["registry"] + q["intended_mirror_suffix"]):
        with reader(repository, q, cloud) as read: content(read, q)
    return {**proof, "status": "redis_chain_verified", "canonical_mirror_verified": True, "approved_registry_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("upstream", "canonical", "chain"))
    args = parser.parse_args()
    try:
        q = policy()
        if args.stage == "chain": result = verify_chain(q, r.Cloud())
        else:
            result = upstream(q)
            if args.stage == "canonical":
                with reader(q["selection_repository"], q) as read: content(read, q)
                result = {**result, "status": "canonical_content_verified"}
        print(json.dumps(result, sort_keys=True)); return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print(json.dumps({"status": "failed", "trusted": False, "reason": "redis_source_or_content_chain_failed"})); return 3


if __name__ == "__main__": raise SystemExit(main())
