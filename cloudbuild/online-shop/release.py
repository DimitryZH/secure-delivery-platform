#!/usr/bin/env python3
"""Bounded catalog-v1 production, independent verification and separate signing."""
import argparse
import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import types
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SDP = "https://github.com/DimitryZH/secure-delivery-platform"
AML = "https://github.com/DimitryZH/application-modernization-lab"
REVISION = "89fd1cde8285761cc2a35dfb22d145adb2eed980"
COMPONENT = "productcatalogservice"
WORKLOAD = "workloads/online-shop"
CONTEXT = "src/" + COMPONENT
SCRIPT = "cloudbuild/online-shop/release.py"
TRUSTED_FILES = (SCRIPT, "cloudbuild/online-shop/catalog-v1.json",
                 "deploy/environments.json", "cloudbuild/scripts/attest-release.py")
PROFILE = {"version": 1, "id": "catalog-v1", "application": "online-shop",
           "repository": AML, "revision": REVISION, "platform": "linux/amd64",
           "required_components": [COMPONENT]}
SHA = r"[0-9a-f]{40}"
DIGEST = r"sha256:[0-9a-f]{64}"
UUID = r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}"


def require(condition, code):
    if not condition:
        raise ValueError(code)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def fingerprint(value):
    return "sha256:" + sha(canonical(value))


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate_json_key")
        result[key] = value
    return result


def decode(data):
    return json.loads(data, object_pairs_hook=unique)


def read(path):
    return decode(Path(path).read_bytes())


def command(args):
    if args[0] == "git":
        # Disposable object stores need no background maintenance. On Windows a
        # detached Git maintenance process can hold their directories open.
        args = ["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", *args[1:]]
    return subprocess.run(args, check=True, capture_output=True).stdout


class Source:
    """Read Git objects only; never read or check out the source working tree."""
    def __init__(self, repo, revision):
        require(re.fullmatch(SHA, revision), "invalid_source_revision")
        self.repo, self.revision = str(repo), revision
        require(self.git("rev-parse", revision + "^{commit}").decode().strip() == revision,
                "source_commit_missing")

    def git(self, *args):
        return command(["git", "--no-optional-locks", "-C", self.repo, *args])

    def blob(self, path):
        require(not path.startswith("/") and ".." not in Path(path).parts, "unsafe_source_path")
        return self.git("show", self.revision + ":" + path)

    def plan(self):
        # Execute only the explicitly reviewed immutable AML planner, never a
        # candidate-provided helper or working-tree copy. It reads Git objects.
        module = types.ModuleType("pinned_aml_planner")
        code = self.blob(WORKLOAD + "/build_plan.py")
        exec(compile(code, "<immutable AML build_plan.py>", "exec"), module.__dict__)
        result = module.plan(self.repo, self.revision, [COMPONENT], "linux/amd64")
        require(result["sourceRevision"] == REVISION and result["toolingRevision"] == REVISION,
                "planner_revision_mismatch")
        component = result["components"]
        require(len(component) == 1 and component[0]["id"] == COMPONENT, "plan_membership")
        require(component[0]["buildContext"] == CONTEXT
                and component[0]["dockerfile"] == CONTEXT + "/Dockerfile"
                and component[0]["target"] is None and component[0]["preparation"] == []
                and component[0]["buildArguments"] == {
                    "SOURCE_REVISION": REVISION, "SKAFFOLD_GO_GCFLAGS": ""}, "plan_settings")
        return result


@contextmanager
def fetched(repository, revision):
    # Fixed canonical URLs are supplied by trusted code, not candidate JSON.
    with tempfile.TemporaryDirectory(prefix="sdp-source-") as directory:
        command(["git", "init", "--bare", directory])
        command(["git", "-C", directory, "fetch", "--no-tags", repository + ".git", revision])
        yield Source(directory, revision)


def policy():
    require(read(HERE / "catalog-v1.json") == PROFILE, "unapproved_profile")
    env = read(ROOT / "deploy/environments.json")
    project, registry, producer = env["project"], env["approved_registry"], env["build_service_account"]
    require(re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", project), "invalid_project")
    require(registry == "us-central1-docker.pkg.dev/" + project + "/secure-delivery",
            "registry_policy_mismatch")
    require(producer == "secure-delivery-build@" + project + ".iam.gserviceaccount.com",
            "producer_policy_mismatch")
    return {"project": project, "region": "us-central1", "registry": registry,
            "producer": "projects/" + project + "/serviceAccounts/" + producer,
            "signer": "projects/" + project + "/serviceAccounts/secure-delivery-attestation@"
                      + project + ".iam.gserviceaccount.com"}


def reviewed_configuration(revision):
    require(re.fullmatch(SHA, revision), "invalid_configuration_revision")
    # Main ancestry is a review boundary, not a branch-name substitution. No
    # --allow-feature or supplied evidence path exists in the live CLI.
    with tempfile.TemporaryDirectory(prefix="sdp-reviewed-") as directory:
        command(["git", "init", "--bare", directory])
        command(["git", "-C", directory, "fetch", "--no-tags", SDP + ".git", "main"])
        command(["git", "-C", directory, "merge-base", "--is-ancestor", revision, "FETCH_HEAD"])
        source = Source(directory, revision)
        for path in TRUSTED_FILES:
            actual = (ROOT / path).read_bytes().replace(b"\r\n", b"\n")
            require(actual == source.blob(path), "unreviewed_execution_files")
    return policy()


def plan_reference(source, plan):
    return {"sha256": fingerprint(plan), "inputs_sha256": fingerprint(plan["components"][0]["inputs"]),
            "planner_sha256": "sha256:" + sha(source.blob(WORKLOAD + "/build_plan.py")),
            "contract_sha256": "sha256:" + sha(source.blob(WORKLOAD + "/build.contract.json")),
            "uri": "git+" + AML + "@" + REVISION + "#" + WORKLOAD + "/build_plan.py"}


def materialize(source, expected_plan, destination):
    plan = source.plan()
    require(fingerprint(plan) == expected_plan, "plan_hash_mismatch")
    component = plan["components"][0]
    files = {row["path"]: row["sha256"] for row in component["inputs"]}
    require(len(files) == len(component["inputs"]), "duplicate_input")
    dockerfile = component["dockerfile"]
    files[dockerfile] = component["dockerfileSha256"]
    ignore = CONTEXT + "/.dockerignore"
    files[ignore] = sha(source.blob(WORKLOAD + "/" + ignore))
    destination = Path(destination)
    require(not destination.exists(), "context_must_not_exist")
    # Only COPY-expanded tracked inputs and build controls enter this new context.
    # Git objects avoid CRLF conversion, hooks, symlinks and untracked additions.
    for path, expected in files.items():
        require(path.startswith(CONTEXT + "/") and ".." not in Path(path).parts,
                "input_path_escape")
        data = source.blob(WORKLOAD + "/" + path)
        require(sha(data) == expected, "input_hash_mismatch")
        target = destination / path[len(CONTEXT) + 1:]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    validate_context(destination, files)
    return plan


def validate_context(destination, files):
    destination = Path(destination)
    entries = list(destination.rglob("*"))
    require(not destination.is_symlink() and all(not p.is_symlink() and (p.is_file() or p.is_dir())
                                               for p in entries), "unsafe_context_entry")
    actual = {p.relative_to(destination).as_posix(): p for p in entries if p.is_file()}
    expected = {p[len(CONTEXT) + 1:]: digest for p, digest in files.items()}
    require(set(actual) == set(expected), "undeclared_context_file")
    for name, path in actual.items():
        require(not path.is_symlink() and sha(path.read_bytes()) == expected[name], "context_bytes_mismatch")


def build_request(p, configuration_revision, plan=None, plan_hash=None):
    require(re.fullmatch(SHA, configuration_revision), "invalid_configuration_revision")
    tag = p["registry"] + "/online-shop-" + COMPONENT + ":" + configuration_revision + "-" + REVISION
    return {
        "source": {"gitSource": {"url": SDP + ".git", "revision": configuration_revision}},
        "serviceAccount": p["producer"], "timeout": "1200s",
        "options": {"logging": "CLOUD_LOGGING_ONLY"},
        "steps": [
            {"id": "materialize-verified-inputs", "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim",
             "entrypoint": "bash", "args": ["-ceu",
                 "apt-get update -qq && apt-get install -y -qq git >/dev/null\n"
                 "python3 " + SCRIPT + " materialize --expected-plan " + (plan_hash or fingerprint(plan))
                 + " --destination /workspace/catalog-context"], "dir": "/workspace"},
            {"id": "build-catalog", "name": "gcr.io/cloud-builders/docker", "dir": "/workspace",
             "env": ["DOCKER_BUILDKIT=1"],
             "args": ["build", "--platform", "linux/amd64", "--build-arg", "SOURCE_REVISION=" + REVISION,
                      "--build-arg", "SKAFFOLD_GO_GCFLAGS=", "-t", tag,
                      "-f", "catalog-context/Dockerfile", "catalog-context"]},
        ], "images": [tag],
    }


def build_url(p, build_id):
    require(re.fullmatch(UUID, build_id), "invalid_build_id")
    return "projects/" + p["project"] + "/locations/" + p["region"] + "/builds/" + build_id


def check_build(build, p, config, plan, build_id):
    """Match authoritative Cloud Build input/execution/output, not log claims."""
    expected = build_request(p, config, plan)
    require(build.get("id") == build_id and build.get("projectId") == p["project"]
            and build.get("name") == build_url(p, build_id), "build_identity_mismatch")
    require(build.get("status") == "SUCCESS" and build.get("finishTime"), "build_not_successful")
    for key in ("source", "serviceAccount", "images", "timeout"):
        require(build.get(key) == expected[key], "build_configuration_mismatch_" + key)
    require(build.get("sourceProvenance", {}).get("resolvedGitSource") == expected["source"]["gitSource"],
            "configuration_source_provenance_missing")
    # Reject all executable additions. Strip only documented service output fields.
    steps = []
    for step in build.get("steps", []):
        require(step.get("status") == "SUCCESS" and step.get("exitCode", 0) == 0, "step_not_successful")
        steps.append({k: v for k, v in step.items()
                      if k not in ("status", "exitCode", "timing", "pullTiming")})
    require(steps == expected["steps"], "unauthorized_build_steps")
    require(build.get("options") == expected["options"], "unauthorized_build_options")
    for key in ("substitutions", "secrets", "availableSecrets", "dependencies", "gitConfig", "artifacts"):
        require(not build.get(key), "unauthorized_build_" + key)
    images = build.get("results", {}).get("images", [])
    require(len(images) == 1 and images[0].get("name") == expected["images"][0]
            and re.fullmatch(DIGEST, images[0].get("digest", "")), "published_image_result_missing")
    return images[0]["digest"]


def candidate(p, config, plan_ref, build_id, digest, image_config):
    result = {"version": 1, "application": "online-shop", "profile": "catalog-v1",
              "profile_sha256": fingerprint(PROFILE),
              "source": {"repository": AML, "revision": REVISION},
              "configuration": {"repository": SDP, "revision": config, "path": SCRIPT,
                  "request_sha256": fingerprint(build_request(p, config, plan_hash=plan_ref["sha256"]))}, "plan": plan_ref,
              "build": {"name": build_url(p, build_id), "id": build_id, "producer": p["producer"]},
              "components": [{"id": COMPONENT, "repository": p["registry"] + "/online-shop-" + COMPONENT,
                              "digest": digest, "platform": "linux/amd64", "config_digest": image_config}]}
    result["release_set_id"] = fingerprint(result)
    return result


def validate_candidate(record, p, config, plan_ref):
    # Exact reconstruction fixes schema and membership against trusted catalog-v1.
    require(isinstance(record, dict), "invalid_candidate")
    require(type(record.get("version")) is int and record["version"] == 1, "invalid_candidate_version")
    payload = {key: value for key, value in record.items() if key != "release_set_id"}
    require(record.get("release_set_id") == fingerprint(payload), "candidate_identity_mismatch")
    components = record.get("components")
    require(isinstance(components, list) and len(components) == 1
            and components[0].get("id") == COMPONENT, "candidate_membership")
    component = components[0]
    require(re.fullmatch(DIGEST, component.get("digest", ""))
            and re.fullmatch(DIGEST, component.get("config_digest", "")), "invalid_digest")
    expected = candidate(p, config, plan_ref, record.get("build", {}).get("id", ""),
                         component["digest"], component["config_digest"])
    require(record == expected, "candidate_policy_or_identity_mismatch")


class Cloud:
    """Live evidence adapter. There is no CLI option to supply offline evidence."""
    def __init__(self):
        gcloud = shutil.which("gcloud")
        require(gcloud is not None, "gcloud_executable_unavailable")
        self.token = command([gcloud, "auth", "print-access-token", "--quiet"]).decode().strip()
        require(bool(self.token), "credentials_unavailable")

    def request(self, url, body=None, registry=False):
        auth = ("Basic " + base64.b64encode(("oauth2accesstoken:" + self.token).encode()).decode()
                if registry else "Bearer " + self.token)
        headers = {"Authorization": auth, "Content-Type": "application/json"}
        if registry:
            headers["Accept"] = ("application/vnd.docker.distribution.manifest.v2+json, "
                                 "application/vnd.oci.image.manifest.v1+json")
        req = urllib.request.Request(url, data=canonical(body) if body is not None else None, headers=headers)
        # Registry blobs may redirect to signed Cloud Storage URLs. Never forward
        # the OAuth token/Basic credentials to a redirect target.
        opener = urllib.request.build_opener(SafeRedirect())
        with opener.open(req, timeout=60) as response:
            return response.read()

    def build(self, p, build_id):
        return decode(self.request("https://cloudbuild.googleapis.com/v1/" + build_url(p, build_id)))

    def image(self, repository, digest):
        host, path = repository.split("/", 1)
        base = "https://" + host + "/v2/" + path
        raw = self.request(base + "/manifests/" + digest, registry=True)
        require("sha256:" + sha(raw) == digest, "registry_manifest_digest_mismatch")
        manifest = decode(raw)
        require(manifest.get("schemaVersion") == 2 and "manifests" not in manifest,
                "single_platform_manifest_required")
        config_digest = manifest["config"]["digest"]
        require(re.fullmatch(DIGEST, config_digest), "invalid_registry_config_digest")
        raw_config = self.request(base + "/blobs/" + config_digest, registry=True)
        require("sha256:" + sha(raw_config) == config_digest, "registry_config_digest_mismatch")
        image = decode(raw_config)
        require(image.get("os") == "linux" and image.get("architecture") == "amd64", "registry_platform_mismatch")
        require(image.get("config", {}).get("Labels", {}).get("org.opencontainers.image.revision") == REVISION,
                "registry_revision_label_mismatch")
        return config_digest


class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        require(target.scheme == "https" and target.hostname == "storage.googleapis.com",
                "unexpected_api_redirect")
        return urllib.request.Request(newurl, headers={"Accept": req.get_header("Accept", "*/*")})


def verify(record, p, config, plan, plan_ref, cloud):
    validate_candidate(record, p, config, plan_ref)
    build_id = record["build"]["id"]
    digest = check_build(cloud.build(p, build_id), p, config, plan, build_id)
    component = record["components"][0]
    require(digest == component["digest"], "build_registry_digest_mismatch")
    actual_config = cloud.image(component["repository"], digest)
    require(actual_config == component["config_digest"], "image_configuration_mismatch")
    return {"version": 1, "release_set_id": record["release_set_id"], "status": "passed",
            "build": record["build"]["name"], "components": [{"id": COMPONENT,
            "artifact": component["repository"] + "@" + digest, "status": "passed"}],
            "verified_at": datetime.now(timezone.utc).isoformat()}


def attestation_helper():
    spec = importlib.util.spec_from_file_location("sample_attestation", ROOT / "cloudbuild/scripts/attest-release.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sign(record, p, config, plan, plan_ref, cloud, helper):
    # Always obtain fresh authoritative evidence here. No success JSON input.
    verification = verify(record, p, config, plan, plan_ref, cloud)
    project = p["project"]
    attestor = "projects/" + project + "/attestors/secure-delivery-verification"
    note = "projects/" + project + "/notes/secure-delivery-verification"
    key = "projects/" + project + "/locations/" + p["region"] + "/keyRings/secure-delivery-attestation/cryptoKeys/verification/cryptoKeyVersions/1"
    public = "//cloudkms.googleapis.com/v1/" + key
    completed = []
    # Do not emit trusted success until every required component has readback and
    # independently validated signature. Failures may leave an occurrence behind.
    for component in verification["components"]:
        artifact = component["artifact"]
        created = helper.sign_and_create(artifact, project, attestor, note, key, public, cloud.token)
        require(re.fullmatch("projects/" + re.escape(project) + r"/occurrences/[A-Za-z0-9_-]+",
                             created.get("name", "")), "invalid_created_occurrence")
        observed = helper.request_json("https://containeranalysis.googleapis.com/v1/" + created["name"], cloud.token)
        reference = helper.inspect_occurrence([observed], artifact, public, note)
        helper.validate_signature(observed, attestor, cloud.token)
        completed.append({"id": component["id"], "artifact": artifact, "occurrence": reference,
                          "signature_verified": True})
    require(len(completed) == len(PROFILE["required_components"]), "partial_signing")
    return {"version": 1, "release_set_id": record["release_set_id"], "status": "trusted",
            "verification": verification, "components": completed,
            "attested_at": datetime.now(timezone.utc).isoformat()}


def signing_request(p, config, object_uri, candidate_sha):
    # Candidate transport is a generation-pinned object in the existing dedicated
    # signing bucket. It is never executable source and cannot select policy.
    require(re.fullmatch(r"gs://" + re.escape(p["project"] + "-attestation-source")
                         + r"/[A-Za-z0-9_/-]+\.json#[1-9][0-9]*", object_uri or ""), "invalid_candidate_object")
    require(re.fullmatch(DIGEST, candidate_sha or ""), "invalid_candidate_transport_hash")
    require(re.fullmatch(SHA, config), "invalid_configuration_revision")
    return {"source": {"gitSource": {"url": SDP + ".git", "revision": config}},
            "serviceAccount": p["signer"], "timeout": "600s",
            "options": {"logging": "CLOUD_LOGGING_ONLY"},
            "steps": [{"id": "independent-verification-and-attestation",
                       "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim", "entrypoint": "bash",
                       "dir": "/workspace", "args": ["-ceu",
                           "apt-get update -qq && apt-get install -y -qq git >/dev/null\n"
                           "gcloud storage cp '" + object_uri + "' /workspace/catalog-candidate.json\n"
                           "echo '" + candidate_sha.removeprefix("sha256:")
                           + "  /workspace/catalog-candidate.json' | sha256sum -c -\n"
                           "python3 " + SCRIPT + " attest --configuration-revision " + config
                           + " --candidate /workspace/catalog-candidate.json"]}]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "materialize", "request", "submit", "candidate", "verify", "attest", "signing-request", "submit-signing"))
    parser.add_argument("--configuration-revision")
    parser.add_argument("--candidate")
    parser.add_argument("--build-id")
    parser.add_argument("--expected-plan")
    parser.add_argument("--destination")
    parser.add_argument("--candidate-object")
    parser.add_argument("--candidate-sha256")
    parser.add_argument("--aml-repo", help="Read-only local Git object source; plan action only")
    args = parser.parse_args()
    try:
        if args.action == "plan" and args.aml_repo:
            print(json.dumps(Source(args.aml_repo, REVISION).plan(), indent=2, sort_keys=True))
            return 0
        require(not args.aml_repo, "local_source_not_allowed_for_live_actions")
        if args.action == "materialize":
            require(args.expected_plan and args.destination, "materialization_arguments_required")
            with fetched(AML, REVISION) as source:
                materialize(source, args.expected_plan, args.destination)
            return 0
        p = reviewed_configuration(args.configuration_revision or "")
        if args.action in ("signing-request", "submit-signing"):
            result = signing_request(p, args.configuration_revision, args.candidate_object, args.candidate_sha256)
            if args.action == "submit-signing":
                cloud = Cloud()
                response = decode(cloud.request("https://cloudbuild.googleapis.com/v1/projects/" + p["project"]
                                  + "/locations/" + p["region"] + "/builds", result))
                result = {"status": "submitted", "operation": response["name"],
                          "build_id": response.get("metadata", {}).get("build", {}).get("id"),
                          "project": p["project"], "region": p["region"]}
            print(json.dumps(result, indent=2, sort_keys=True))
            return 0
        with fetched(AML, REVISION) as source:
            plan = source.plan()
            ref = plan_reference(source, plan)
        if args.action == "plan":
            result = plan
        elif args.action == "request":
            result = build_request(p, args.configuration_revision, plan)
        elif args.action == "submit":
            cloud = Cloud()
            # One bounded build, no retries. Observe the returned operation separately.
            result = decode(cloud.request("https://cloudbuild.googleapis.com/v1/projects/" + p["project"]
                            + "/locations/" + p["region"] + "/builds", build_request(p, args.configuration_revision, plan)))
            result = {"status": "submitted", "operation": result["name"],
                      "build_id": result.get("metadata", {}).get("build", {}).get("id"),
                      "project": p["project"], "region": p["region"]}
        else:
            cloud = Cloud()
            if args.action == "candidate":
                build = cloud.build(p, args.build_id or "")
                digest = check_build(build, p, args.configuration_revision, plan, args.build_id)
                config_digest = cloud.image(p["registry"] + "/online-shop-" + COMPONENT, digest)
                result = candidate(p, args.configuration_revision, ref, args.build_id, digest, config_digest)
            else:
                require(args.candidate, "candidate_path_required")
                record = read(args.candidate)
                if args.action == "verify":
                    result = verify(record, p, args.configuration_revision, plan, ref, cloud)
                else:
                    # This action must run in separately authorized signing execution.
                    result = sign(record, p, args.configuration_revision, plan, ref, cloud, attestation_helper())
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except (ValueError, KeyError, TypeError, AttributeError, OSError, subprocess.CalledProcessError):
        # Never publish raw API bodies, subprocess stderr, tokens, or partial trust.
        print(json.dumps({"version": 1, "action": args.action, "status": "failed",
                          "reason": "required_policy_or_evidence_check_failed", "trusted": False}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
