#!/usr/bin/env python3
"""Versioned complete shop release path. catalog-v1 remains an independent API."""
import argparse
import base64
import copy
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import types
import urllib.parse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
    return result

r = module("catalog_release", HERE / "release.py")
support = module("collector_support", HERE / "collector.py")
legacy = module("catalog_deployment", ROOT / "deploy/online-shop/workflow.py")
require = r.require
SCRIPT = "cloudbuild/online-shop/complete.py"
PROFILE_SHA = "4766ad8f2c1d3c771fb9c02a6c81a76f152fdf723de7c0013fb910a5f4143126"
REDIS_POLICY_SHA = "c3e35a722662e7695df196e3141b77cb27a31def336a7c01a505c0e3f2519dea"
APPS = tuple(sorted("frontend productcatalogservice cartservice currencyservice recommendationservice adservice checkoutservice shippingservice paymentservice emailservice".split()))
MEMBERS = (*APPS, "redis-cart")
TRUST_FILES = tuple(dict.fromkeys((*legacy.TRUST_FILES, SCRIPT, "cloudbuild/online-shop/complete-v1.json",
    "cloudbuild/online-shop/redis-policy-v1.json", "deploy/online-shop/complete.py",
    "deploy/online-shop/complete-runtime-v1.json", "deploy/online-shop/complete-skaffold.yaml",
    "deploy/online-shop/complete-acceptance.py", "cloudbuild/online-shop/complete-candidate-v1.schema.json")))

def profile():
    raw = (HERE / "complete-v1.json").read_bytes().replace(b"\r\n", b"\n")
    require(r.sha(raw) == PROFILE_SHA, "unreviewed_complete_profile")
    return r.decode(raw)

def redis_policy():
    raw = (HERE / "redis-policy-v1.json").read_bytes().replace(b"\r\n", b"\n")
    require(r.sha(raw) == REDIS_POLICY_SHA, "unreviewed_redis_policy")
    return r.decode(raw)

def redis_admission():
    # The pinned AML mirror has no established producing source/build lineage.
    # No caller assertion, content equality, existing occurrence or publisher tag
    # can turn it into an approved dependency. Resolution needs a reviewed policy
    # revision AND an independently verifiable adoption path, not a CLI override.
    q = redis_policy()
    require(q["admission_decision"] == "approved_verified_provenance"
            and q["mirror_or_sign_authorized"] is True, "redis_provenance_unresolved_admission_blocked")
    raise ValueError("redis_approved_adoption_requires_reviewed_profile_revision")

def reviewed(revision):
    require(re.fullmatch(r.SHA, revision or ""), "configuration_revision_required")
    with r.fetched(r.SDP, revision) as source:
        source.git("fetch", "--no-tags", r.SDP + ".git", "main")
        source.git("merge-base", "--is-ancestor", revision, "FETCH_HEAD")
        for name in TRUST_FILES:
            require((ROOT / name).read_bytes().replace(b"\r\n", b"\n") == source.blob(name), "unreviewed_complete_files")
    profile(); redis_policy()

def plans(source):
    q = profile()
    require(source.revision == r.REVISION, "wrong_aml_revision")
    for name, digest in q["contracts_sha256"].items():
        require("sha256:" + r.sha(source.blob(r.WORKLOAD + "/" + name)) == digest, "aml_contract_hash_mismatch")
    planner = types.ModuleType("immutable_complete_planner")
    exec(compile(source.blob(r.WORKLOAD + "/build_plan.py"), "<immutable AML planner>", "exec"), planner.__dict__)
    full = planner.plan(source.repo, r.REVISION, list(APPS), "linux/amd64")
    require(full["sourceRevision"] == full["toolingRevision"] == r.REVISION and full["platform"] == "linux/amd64", "wrong_plan_revision")
    require([x["id"] for x in full["components"]] == list(APPS), "plan_membership")
    result = {}
    for item in full["components"]:
        identity = item["id"]
        arguments = {"SOURCE_REVISION": r.REVISION}
        if identity in ("frontend", "checkoutservice", "productcatalogservice", "shippingservice"):
            arguments["SKAFFOLD_GO_GCFLAGS"] = ""
        context = q["build_contexts"][identity]
        require(item["buildContext"] == context and item["dockerfile"] == context + "/Dockerfile"
                and item["target"] is None and item["preparation"] == [] and item["buildArguments"] == arguments, "component_plan_settings")
        result[identity] = {**full, "components": [item]}
    return result

def references(source, value):
    return {identity: r.plan_reference(source, plan) for identity, plan in value.items()}

def materialize(source, identity, expected, destination):
    require(identity in APPS, "unknown_application_component")
    plan = plans(source)[identity]
    require(r.fingerprint(plan) == expected, "component_plan_hash_mismatch")
    item = plan["components"][0]; context = item["buildContext"]
    files = {row["path"]: row["sha256"] for row in item["inputs"]}
    require(len(files) == len(item["inputs"]), "duplicate_input")
    files[item["dockerfile"]] = item["dockerfileSha256"]
    ignore = context + "/.dockerignore"
    if source.git("ls-tree", "--name-only", source.revision, "--", r.WORKLOAD + "/" + ignore).strip():
        files[ignore] = r.sha(source.blob(r.WORKLOAD + "/" + ignore))
    target = Path(destination)
    require(not target.exists(), "context_must_not_exist")
    for name, digest in files.items():
        require(name.startswith(context + "/") and ".." not in Path(name).parts, "input_path_escape")
        raw = source.blob(r.WORKLOAD + "/" + name)
        require(r.sha(raw) == digest, "input_hash_mismatch")
        mode = source.git("ls-tree", source.revision, "--", r.WORKLOAD + "/" + name).split()[0].decode()
        require(mode in ("100644", "100755"), "unsafe_input_mode")
        path = target / name[len(context) + 1:]; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw); path.chmod(0o755 if mode == "100755" else 0o644)
    actual = {p.relative_to(target).as_posix(): p for p in target.rglob("*") if p.is_file()}
    require(not target.is_symlink() and all(not p.is_symlink() for p in target.rglob("*")), "unsafe_context_entry")
    require(set(actual) == {name[len(context) + 1:] for name in files}, "undeclared_context_file")
    require(all(r.sha(actual[name[len(context) + 1:]].read_bytes()) == digest for name, digest in files.items()), "context_bytes_mismatch")

def build_request(identity, revision, plan):
    require(identity in APPS and identity != "productcatalogservice", "catalog_must_reuse_accepted_artifact")
    require(re.fullmatch(r.SHA, revision or ""), "invalid_configuration_revision")
    item = plan["components"][0]
    require(item["id"] == identity, "component_plan_mismatch")
    tag = r.policy()["registry"] + "/online-shop-" + identity + ":" + revision + "-" + r.REVISION
    args = ["build", "--platform", "linux/amd64"]
    for key, value in sorted(item["buildArguments"].items()): args += ["--build-arg", key + "=" + value]
    args += ["-t", tag, "-f", "component-context/Dockerfile", "component-context"]
    return {"source": {"gitSource": {"url": r.SDP + ".git", "revision": revision}}, "serviceAccount": r.policy()["producer"],
        "timeout": "1800s", "options": {"logging": "CLOUD_LOGGING_ONLY"}, "tags": ["complete-shop-v1", identity, revision],
        "steps": [{"id": "materialize-verified-" + identity, "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim",
            "entrypoint": "bash", "dir": "/workspace", "args": ["-ceu", "apt-get update -qq && apt-get install -y -qq git >/dev/null\n"
                "python3 " + SCRIPT + " materialize --component " + identity + " --expected-plan " + r.fingerprint(plan)
                + " --destination /workspace/component-context"]},
            {"id": "build-" + identity, "name": "gcr.io/cloud-builders/docker", "dir": "/workspace", "env": ["DOCKER_BUILDKIT=1"], "args": args}],
        "images": [tag]}

def check_build(value, identity, revision, plan, build_id):
    expected = build_request(identity, revision, plan)
    name = r.build_url(r.policy(), build_id)
    numeric = name.replace("/" + r.policy()["project"] + "/", "/" + r.policy()["project_number"] + "/", 1)
    require(value.get("name") in (name, numeric) and value.get("id") == build_id
            and value.get("projectId") == r.policy()["project"] and value.get("status") == "SUCCESS" and value.get("finishTime"), "build_identity_or_status")
    for field in ("source", "serviceAccount", "timeout", "images", "tags"):
        require(value.get(field) == expected[field], "component_build_configuration_" + field)
    require(value.get("sourceProvenance", {}).get("resolvedGitSource") == expected["source"]["gitSource"], "source_provenance_mismatch")
    require(value.get("options") in (expected["options"], {**expected["options"], "pool": {}, "workerRelease": "legacy"}), "unexpected_build_options")
    require(value.get("artifacts") in (None, {}, {"images": expected["images"]}), "unexpected_build_artifacts")
    require(not any(value.get(k) for k in ("substitutions", "secrets", "availableSecrets", "dependencies", "gitConfig")), "unexpected_build_inputs")
    steps = value.get("steps", [])
    require(all(s.get("status") == "SUCCESS" and s.get("exitCode", 0) == 0 for s in steps), "component_step_failed")
    require([{k:v for k,v in s.items() if k not in ("status", "exitCode", "timing", "pullTiming")} for s in steps] == expected["steps"], "unexpected_component_steps")
    images = value.get("results", {}).get("images", [])
    require(len(images) == 1 and images[0].get("name") == expected["images"][0] and re.fullmatch(r.DIGEST, images[0].get("digest", "")), "component_build_image_binding")
    return images[0]["digest"]

def app_record(identity, revision, ref, build_id, digest, config_digest):
    return {"id": identity, "role": "application", "source": {"repository": r.AML, "revision": r.REVISION},
        "configuration": {"repository": r.SDP, "revision": revision, "path": r.SCRIPT if identity == "productcatalogservice" else SCRIPT},
        "plan": ref, "build": {"id": build_id, "name": r.build_url(r.policy(), build_id), "producer": r.policy()["producer"]},
        "repository": r.policy()["registry"] + "/online-shop-" + identity, "digest": digest, "config_digest": config_digest, "platform": "linux/amd64"}

def dependency_record():
    q = redis_policy()
    return {"id": "redis-cart", "role": "dependency", "repository": r.policy()["registry"] + q["intended_mirror_suffix"],
        "digest": q["manifest_digest"], "config_digest": q["config_digest"], "platform": q["platform"],
        "source": {"kind": "selection_contract_not_publisher_provenance", **q["selection_source"], "contracts_sha256": q["selection_contracts_sha256"]},
        "build": {"kind": "external_unresolved", "producing_source": None, "producing_build": None},
        "admission_decision": q["admission_decision"]}

def candidate(revision, applications):
    require(re.fullmatch(r.SHA, revision or ""), "invalid_configuration_revision")
    require(type(applications) is list and [x.get("id") for x in applications] == list(APPS), "complete_membership_required")
    value = {"version": 2, "application": "online-shop", "profile": "complete-shop-v1", "profile_sha256": "sha256:" + PROFILE_SHA,
        "configuration_revision": revision, "components": applications + [dependency_record()]}
    return {**value, "release_set_id": r.fingerprint(value)}

def validate_candidate(record, revision, refs):
    require(type(record) is dict and type(record.get("version")) is int and record["version"] == 2, "invalid_complete_candidate_version")
    require(record.get("release_set_id") == r.fingerprint({k:v for k,v in record.items() if k != "release_set_id"}), "complete_candidate_identity_mismatch")
    rows = record.get("components")
    require(type(rows) is list and [x.get("id") for x in rows] == list(MEMBERS), "complete_membership_required")
    expected = []
    for row in rows[:-1]:
        identity = row["id"]
        require(type(row.get("build")) is dict and re.fullmatch(r.UUID, row["build"].get("id", "")), "invalid_component_build")
        require(all(re.fullmatch(r.DIGEST, row.get(k, "")) for k in ("digest", "config_digest")), "invalid_component_digest")
        accepted = legacy.policy()["accepted_release"]
        config = accepted["configuration_revision"] if identity == "productcatalogservice" else revision
        if identity == "productcatalogservice":
            require(row["build"]["id"] == accepted["build_id"] and row["digest"] == accepted["manifest_digest"], "unaccepted_catalog_reuse")
        expected.append(app_record(identity, config, refs[identity], row["build"]["id"], row["digest"], row["config_digest"]))
    require(r.canonical(record) == r.canonical(candidate(revision, expected)), "complete_candidate_policy_mismatch")

def catalog_candidate(cloud):
    q = legacy.policy()["accepted_release"]
    name = "online-shop/catalog-v1/" + q["configuration_revision"] + "/" + q["build_id"] + "/candidate.json"
    raw = cloud.request("https://storage.googleapis.com/storage/v1/b/" + r.policy()["project"] + "-attestation-source/o/"
                        + urllib.parse.quote(name, safe="") + "?alt=media&generation=" + q["candidate_generation"])
    require("sha256:" + r.sha(raw) == q["candidate_transport_sha256"], "catalog_transport_mismatch")
    record = r.decode(raw)
    # The occurrence reference is fixed accepted evidence, not an operator claim.
    legacy.verify_application(record, "projects/" + r.policy()["project"] + "/occurrences/c274dea4-483a-43d6-b241-ed4d593e617e", cloud)
    return record

def observe_candidate(revision, build_ids, value, refs, cloud):
    require(type(build_ids) is dict and set(build_ids) == set(APPS) - {"productcatalogservice"}, "nine_component_build_ids_required")
    catalog = catalog_candidate(cloud); rows = []
    for identity in APPS:
        if identity == "productcatalogservice":
            c = catalog["components"][0]
            require(catalog["plan"] == refs[identity], "catalog_plan_not_reusable")
            rows.append(app_record(identity, catalog["configuration"]["revision"], refs[identity], catalog["build"]["id"], c["digest"], c["config_digest"]))
        else:
            build_id = build_ids[identity]
            digest = check_build(cloud.build(r.policy(), build_id), identity, revision, value[identity], build_id)
            config = cloud.image(r.policy()["registry"] + "/online-shop-" + identity, digest)
            rows.append(app_record(identity, revision, refs[identity], build_id, digest, config))
    return candidate(revision, rows)

def verify(record, revision, value, refs, cloud):
    validate_candidate(record, revision, refs)  # All supplied structure checked before cloud calls.
    redis_admission()  # Known lineage blocker is not turned into evidence success.
    catalog = catalog_candidate(cloud)
    outcomes = []
    for row in record["components"][:-1]:
        identity = row["id"]
        if identity == "productcatalogservice":
            require(row["config_digest"] == catalog["components"][0]["config_digest"], "catalog_config_not_reusable")
        else:
            digest = check_build(cloud.build(r.policy(), row["build"]["id"]), identity, revision, value[identity], row["build"]["id"])
            require(digest == row["digest"] and cloud.image(row["repository"], digest) == row["config_digest"], "component_build_registry_binding")
        outcomes.append({"id": identity, "artifact": row["repository"] + "@" + row["digest"], "status": "passed"})
    # A reviewed Redis adoption implementation must replace the current lineage
    # blocker before this point becomes reachable with the real pinned policy.
    inspect_redis(record["components"][-1]["repository"])
    outcomes.append({"id": "redis-cart", "artifact": record["components"][-1]["repository"] + "@" + redis_policy()["manifest_digest"], "status": "passed"})
    return {"version": 2, "release_set_id": record["release_set_id"], "status": "passed", "components": outcomes, "verified_at": datetime.now(timezone.utc).isoformat()}

def inspect_redis(repository=None):
    q = redis_policy()
    repository = repository or q["selection_repository"]
    require(repository in (q["selection_repository"], r.policy()["registry"] + q["intended_mirror_suffix"]), "unapproved_redis_repository")
    with tempfile.TemporaryDirectory(prefix="sdp-redis-read-") as directory:
        env = support.clean_env(); env["DOCKER_CONFIG"] = directory
        executable = support.tool("crane")
        if repository.startswith(r.policy()["registry"] + "/"):
            cloud = r.Cloud()
            support.run([executable, "auth", "login", repository.split("/")[0], "-u", "oauth2accesstoken", "--password-stdin"], env=env, input=(cloud.token + "\n").encode())
        raw = support.run([executable, "manifest", repository + "@" + q["manifest_digest"]], env=env)
        require("sha256:" + r.sha(raw) == q["manifest_digest"], "redis_manifest_hash")
        manifest = r.decode(raw)
        require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2 and "manifests" not in manifest, "redis_manifest_required")
        support.descriptor(manifest["config"])
        require(manifest["config"]["digest"] == q["config_digest"], "redis_config_binding")
        descriptors = [manifest["config"], *manifest["layers"]]
        for item in descriptors:
            support.descriptor(item)
            data = support.run([executable, "blob", repository + "@" + item["digest"]], env=env)
            require("sha256:" + r.sha(data) == item["digest"] and len(data) == item["size"], "redis_blob_hash_or_size")
            if item is manifest["config"]:
                config = r.decode(data)
                require(config.get("os") == "linux" and config.get("architecture") == "amd64", "redis_platform")
    return {"status": "content_verified_untrusted", "platform": "linux/amd64", "manifest_digest": q["manifest_digest"],
        "config_digest": q["config_digest"], "layers_verified": len(manifest["layers"]), "publisher_provenance": "unresolved",
        "admission_decision": q["admission_decision"], "mirror_or_sign_performed": False}

def existing_occurrences(cloud, artifacts):
    token = ""; seen = set(); found = {artifact: [] for artifact in artifacts}
    attestor, note, key, public = support.authority(); helper = r.attestation_helper()
    for _ in range(100):
        query = urllib.parse.urlencode({"pageSize": 100, "pageToken": token})
        data = r.decode(cloud.request("https://containeranalysis.googleapis.com/v1/" + note + "/occurrences?" + query))
        for observed in data.get("occurrences", []):
            artifact = observed.get("resourceUri", "").removeprefix("https://")
            if artifact in found:
                name = observed.get("name", "")
                require(re.fullmatch(r"projects/[A-Za-z0-9-]+/occurrences/[A-Za-z0-9_-]+", name), "invalid_occurrence_reference")
                actual = r.decode(cloud.request("https://containeranalysis.googleapis.com/v1/" + name))
                require(helper.inspect_occurrence([actual], artifact, public, note) == name, "complete_occurrence_subject_mismatch")
                helper.validate_signature(actual, attestor, cloud.token)
                found[artifact].append(name)
        token = data.get("nextPageToken", "")
        if not token: return found
        require(token not in seen, "occurrence_pagination_cycle"); seen.add(token)
    raise ValueError("complete_occurrence_listing_incomplete")

def attest(record, revision, value, refs, cloud, *, inspect=False):
    if not inspect: support.signer_identity()
    verification = verify(record, revision, value, refs, cloud)
    artifacts = [row["artifact"] for row in verification["components"]]
    found = existing_occurrences(cloud, artifacts)
    helper = r.attestation_helper(); attestor, note, key, public = support.authority()
    outcomes = []
    for item in verification["components"]:
        artifact = item["artifact"]
        if not found[artifact]:
            require(not inspect, "complete_attestation_missing")
            try:
                helper.sign_and_create(artifact, r.policy()["project"], attestor, note, key, public, cloud.token)
            except (OSError, ValueError, subprocess.SubprocessError):
                recovered = existing_occurrences(cloud, artifacts)
                require(bool(recovered[artifact]), "complete_signing_uncertain_inspect_before_retry")
            found = existing_occurrences(cloud, artifacts)
        require(bool(found[artifact]), "complete_occurrence_missing_after_write")
        outcomes.append({**item, "occurrence": sorted(found[artifact])[0], "signature_verified": True})
    require(len(outcomes) == len(MEMBERS), "partial_complete_signing")
    return {"version": 2, "release_set_id": record["release_set_id"], "status": "trusted", "components": outcomes}

def signing_request(revision, uri, digest):
    require(re.fullmatch(r.SHA, revision or ""), "configuration_revision_required")
    require(re.fullmatch(r"gs://" + re.escape(r.policy()["project"] + "-attestation-source") + r"/complete-shop-v1/[A-Za-z0-9_/-]+\.json#[1-9][0-9]*", uri or ""), "invalid_complete_candidate_object")
    require(re.fullmatch(r.DIGEST, digest or ""), "invalid_candidate_transport_hash")
    return {"source": {"gitSource": {"url": r.SDP + ".git", "revision": revision}}, "serviceAccount": r.policy()["signer"],
        "timeout": "1800s", "options": {"logging": "CLOUD_LOGGING_ONLY"}, "tags": ["complete-shop-sign-v1", revision, digest[7:]],
        "steps": [{"id": "independent-complete-verification-and-signing", "name": "gcr.io/google.com/cloudsdktool/cloud-sdk:slim", "entrypoint": "bash", "dir": "/workspace",
            "args": ["-ceu", "apt-get update -qq && apt-get install -y -qq git >/dev/null\n"
                "gcloud storage cp '" + uri + "' /workspace/complete-candidate.json\n"
                "echo '" + digest[7:] + "  /workspace/complete-candidate.json' | sha256sum -c -\n"
                "python3 " + SCRIPT + " attest --configuration-revision " + revision + " --candidate /workspace/complete-candidate.json"]}]}

def submit_once(cloud, request):
    base = "https://cloudbuild.googleapis.com/v1/projects/" + r.policy()["project"] + "/locations/us-central1/builds"
    def lookup():
        found = []; token = ""; seen = set()
        for _ in range(100):
            query = urllib.parse.urlencode({"filter": " AND ".join('tags="' + x + '"' for x in request["tags"]), "pageSize": 100, "pageToken": token})
            data = r.decode(cloud.request(base + "?" + query))
            for build in data.get("builds", []):
                steps = [{k:v for k,v in s.items() if k not in ("status", "exitCode", "timing", "pullTiming")} for s in build.get("steps", [])]
                require(steps == request["steps"] and all(build.get(k) == request[k] for k in ("source", "serviceAccount", "timeout", "tags")), "unexpected_matching_complete_build")
                require(build.get("options") in (request["options"], {**request["options"], "pool": {}, "workerRelease": "legacy"})
                        and not any(build.get(k) for k in ("substitutions", "secrets", "availableSecrets", "dependencies", "gitConfig")), "unexpected_matching_complete_options")
                require(build.get("images", []) == request.get("images", [])
                        and build.get("artifacts") in (None, {}, {"images": request.get("images", [])}), "unexpected_matching_complete_artifacts")
                found.append({"id": build["id"], "status": build["status"]})
            token = data.get("nextPageToken", "")
            if not token: return found
            require(token not in seen, "build_pagination_cycle"); seen.add(token)
        raise ValueError("complete_build_listing_incomplete")
    found = lookup()
    if found: return {"status": "existing_builds", "builds": found, "resubmitted": False}
    try: return {"status": "submitted", "operation": r.decode(cloud.request(base, request)), "resubmitted": False}
    except (OSError, ValueError):
        found = lookup()
        require(bool(found), "complete_submission_uncertain_do_not_resubmit")
        return {"status": "recovered_builds", "builds": found, "resubmitted": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "materialize", "request", "submit", "candidate", "verify", "attest", "inspect", "signing-request", "submit-signing", "inspect-redis"))
    for name in ("configuration-revision", "component", "expected-plan", "destination", "build-ids", "candidate", "candidate-object", "candidate-sha256", "aml-repo"):
        parser.add_argument("--" + name)
    args = parser.parse_args()
    try:
        if args.action == "inspect-redis":
            require(not args.aml_repo, "local_source_not_allowed")
            result = inspect_redis()
        elif args.action == "plan" and args.aml_repo:
            result = plans(r.Source(args.aml_repo, r.REVISION))
        elif args.action == "materialize":
            require(args.component and args.expected_plan and args.destination, "materialization_arguments_required")
            with r.fetched(r.AML, r.REVISION) as source: materialize(source, args.component, args.expected_plan, args.destination)
            result = {"status": "materialized", "component": args.component}
        else:
            require(not args.aml_repo, "local_source_not_allowed_for_live_actions")
            reviewed(args.configuration_revision)
            if args.action in ("signing-request", "submit-signing"):
                redis_admission()
                request = signing_request(args.configuration_revision, args.candidate_object, args.candidate_sha256)
                result = request if args.action == "signing-request" else submit_once(r.Cloud(), request)
            else:
                with r.fetched(r.AML, r.REVISION) as source:
                    value = plans(source); refs = references(source, value)
                if args.action == "plan": result = value
                elif args.action in ("request", "submit"):
                    request = build_request(args.component, args.configuration_revision, value[args.component])
                    result = request if args.action == "request" else submit_once(r.Cloud(), request)
                elif args.action == "candidate": result = observe_candidate(args.configuration_revision, r.read(args.build_ids), value, refs, r.Cloud())
                else:
                    record = r.read(args.candidate)
                    validate_candidate(record, args.configuration_revision, refs)
                    redis_admission()  # No credential/evidence/signing calls for a known blocked dependency.
                    cloud = r.Cloud()
                    result = (verify(record, args.configuration_revision, value, refs, cloud) if args.action == "verify"
                              else attest(record, args.configuration_revision, value, refs, cloud, inspect=args.action == "inspect"))
        print(json.dumps(result, sort_keys=True)); return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError):
        print(json.dumps({"status": "failed", "trusted": False, "reason": "complete_policy_or_evidence_check_failed"})); return 1

if __name__ == "__main__": raise SystemExit(main())
