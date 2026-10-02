#!/usr/bin/env python3
"""Prepare a verified release; execute only as the separate deployment authority."""
import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verification", ROOT / "cloudbuild/scripts/verify-release-metadata.py")
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=verification.unique_object)


def validate(record, policy, environment, reviewed):
    if environment not in policy["environments"]:
        raise ValueError("unsupported_environment")
    if policy["environments"][environment]["namespace"] != environment:
        raise ValueError("environment_namespace_mismatch")
    identity, errors = verification.verify(record, policy["approved_registry"])
    if errors:
        raise ValueError(",".join(errors))
    if record["image_uri"] != identity["artifact_identity"] or not record["image_uri"].startswith(policy["approved_registry"] + "/sample-service@"):
        raise ValueError("sample_service_digest_pinned_image_required")
    if record["source_repository"] != policy["source_repository"] or record["build_service_account"] != policy["build_service_account"]:
        raise ValueError("unexpected_release_producer")
    if policy["deployment_service_account"] == policy["build_service_account"]:
        raise ValueError("deployment_authority_must_be_separate")
    if record.get("verification_status") != "passed" or record.get("errors", []) != []:
        raise ValueError("verification_not_passed")
    timestamp = record.get("verification_timestamp")
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise ValueError("invalid_verification_timestamp")
    if datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00").tzinfo is None:
        raise ValueError("invalid_verification_timestamp")
    if not re.fullmatch(r"projects/" + re.escape(policy["project"]) + r"/occurrences/[A-Za-z0-9_-]+", record.get("trust_signal_ref", "")):
        raise ValueError("invalid_trust_signal_ref")
    if record.get("target_environment") != environment:
        raise ValueError("target_environment_mismatch")
    if policy["environments"][environment]["review_required"] and not reviewed:
        raise ValueError("environment_review_required")
    return identity


def render(record, policy, environment):
    values = {
        "ENVIRONMENT": environment, "COMMIT_SHA": record["commit_sha"],
        "BUILD_ID": record["build_id"], "IMAGE_DIGEST": record["image_digest"],
        "VERIFICATION_STATUS": record["verification_status"], "IMAGE": record["image_uri"],
        "SOURCE_REPOSITORY": record["source_repository"], "BUILD_SERVICE_ACCOUNT": record["build_service_account"],
        "VERIFICATION_TIMESTAMP": record["verification_timestamp"], "TRUST_SIGNAL_REF": record["trust_signal_ref"],
        "DEPLOYMENT_AUTHORITY": policy["deployment_service_account"],
    }
    documents = []
    for name in ("deployment.yaml", "service.yaml"):
        text = (ROOT / "deploy/manifests/base" / name).read_text(encoding="utf-8")
        for key, value in values.items():
            text = text.replace("REPLACE_WITH_" + key, json.dumps(value))
        if "REPLACE_WITH_" in text or "break-glass" in text:
            raise ValueError("invalid_rendered_manifest")
        documents.append(text)
    return "\n---\n".join(documents)


def run(command):
    # Never include stderr or command arguments in errors: token-bearing
    # kubectl commands must not leak credentials into release records.
    executable = shutil.which(command[0])
    if executable is None:
        raise ValueError("executable_not_found:" + command[0])
    completed = subprocess.run([executable, *command[1:]], capture_output=True, text=True, shell=False)
    if completed.returncode:
        raise ValueError("command_failed:" + command[0] + ":exit=" + str(completed.returncode))
    return completed.stdout


def execute(manifest, policy, environment):
    cloud = ["gcloud", "--project=" + policy["project"], "--billing-project=" + policy["project"],
             "--impersonate-service-account=" + policy["deployment_service_account"], "--quiet"]
    cluster = json.loads(run(cloud + ["container", "clusters", "describe", policy["cluster"],
                                   "--location=" + policy["location"], "--format=json"]))
    if cluster.get("binaryAuthorization", {}).get("evaluationMode") != "PROJECT_SINGLETON_POLICY_ENFORCE":
        raise ValueError("cluster_enforcement_not_enabled")
    token = run(cloud + ["auth", "print-access-token"]).strip()
    if not token:
        raise ValueError("deployment_token_missing")
    with tempfile.TemporaryDirectory() as directory:
        ca = Path(directory) / "ca.pem"
        ca.write_bytes(base64.b64decode(cluster["masterAuth"]["clusterCaCertificate"], validate=True))
        kubeconfig = Path(directory) / "kubeconfig.json"
        kubeconfig.write_text(json.dumps({"apiVersion": "v1", "kind": "Config",
                                         "clusters": [], "contexts": [], "users": []}), encoding="utf-8")
        command = ["kubectl", "--kubeconfig=" + str(kubeconfig),
                   "--server=https://" + cluster["endpoint"], "--certificate-authority=" + str(ca),
                   "--token=" + token, "--request-timeout=30s", "--namespace=" + environment]
        namespace = json.loads(run(command + ["get", "namespace", environment, "-o", "json"]))
        if namespace["metadata"]["name"] != environment:
            raise ValueError("namespace_mismatch")
        run(command + ["apply", "-f", str(manifest)])
        run(command + ["rollout", "status", "deployment/sample-service", "--timeout=120s"])
        deployment = json.loads(run(command + ["get", "deployment", "sample-service", "-o", "json"]))
        status = deployment.get("status", {})
        if (status.get("observedGeneration", 0) < deployment["metadata"]["generation"]
                or status.get("updatedReplicas", 0) != 1 or status.get("availableReplicas", 0) < 1):
            raise ValueError("runtime_rollout_not_ready")
        return deployment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--environment", required=True, choices=("dev", "stage", "prod"))
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reviewed", action="store_true", help="Operator confirms review for stage/prod; not an automated approval")
    parser.add_argument("--execute", action="store_true", help="Apply and wait using deploy service-account impersonation")
    args = parser.parse_args()
    result = {"deployment_status": "failed", "target_environment": args.environment}
    output = Path(args.output_dir)
    try:
        policy = load(ROOT / "deploy/environments.json")
        record = load(args.metadata)
        identity = validate(record, policy, args.environment, args.reviewed)
        if args.execute and record["trust_signal_ref"].endswith("/SYNTHETIC-EXAMPLE"):
            raise ValueError("synthetic_example_cannot_be_deployed")
        result.update(**identity, verification_status=record["verification_status"],
                      verification_timestamp=record["verification_timestamp"], trust_signal_ref=record["trust_signal_ref"],
                      target_namespace=args.environment, deployment_service_account=policy["deployment_service_account"],
                      operator_review_status="reviewed" if args.reviewed else "not_required")
        output.mkdir(parents=True, exist_ok=True)
        manifest = output / "sample-service.yaml"
        manifest.write_text(render(record, policy, args.environment), encoding="utf-8")
        if args.execute:
            deployment = execute(manifest, policy, args.environment)
            if deployment["spec"]["template"]["spec"]["containers"][0]["image"] != record["image_uri"]:
                raise ValueError("runtime_digest_mismatch")
            result.update(deployment_status="deployed", promotion_state="deployed",
                          deployed_namespace=args.environment,
                          deployed_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                          deployment_uid=deployment["metadata"]["uid"])
        else:
            result.update(deployment_status="prepared", promotion_state="prepared")
    except (OSError, ValueError, KeyError, TypeError) as error:
        result["error"] = str(error)
    output.mkdir(parents=True, exist_ok=True)
    (output / "deployment-result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 1 if result["deployment_status"] == "failed" else 0


if __name__ == "__main__":
    raise SystemExit(main())
