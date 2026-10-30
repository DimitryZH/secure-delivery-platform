#!/usr/bin/env python3
"""Read-only release verification, local dev rendering and eligibility. No deployment."""
import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import urllib.parse

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


r = module("catalog_release", ROOT / "cloudbuild/online-shop/release.py")
support = module("collector_adoption", ROOT / "cloudbuild/online-shop/collector.py")
sample = module("sample_preflight", ROOT / "deploy/clouddeploy/release-preflight.py")
require = r.require
MAX_AGE, MARGIN = sample.MAX_AGE, sample.PROTECTION_MARGIN
TRUST_FILES = (*r.TRUSTED_FILES, "deploy/online-shop/workflow.py", "deploy/online-shop/policy.json",
               "deploy/online-shop/collector.json", "deploy/online-shop/skaffold.yaml", "deploy/online-shop/acceptance.py",
               "deploy/clouddeploy/release-preflight.py", "deploy/deploy-release.py", "cloudbuild/scripts/verify-release-metadata.py",
               "cloudbuild/online-shop/collector.py", "cloudbuild/online-shop/collector-tools.json")


def policy():
    return r.read(HERE / "policy.json")


def reviewed(revision):
    require(re.fullmatch(r.SHA, revision or ""), "deployment_revision_required")
    with r.fetched(r.SDP, revision) as source:
        # Check ancestry separately; fetching a commit alone proves no review.
        source.git("fetch", "--no-tags", r.SDP + ".git", "main")
        source.git("merge-base", "--is-ancestor", revision, "FETCH_HEAD")
        for name in TRUST_FILES:
            require((ROOT / name).read_bytes().replace(b"\r\n", b"\n") == source.blob(name),
                    "unreviewed_deployment_files")
    return r.policy()


def candidate_policy(record, plan_ref=None):
    require(type(record) is dict, "invalid_candidate")
    require(type(record.get("plan")) is dict, "invalid_candidate_plan")
    if plan_ref is None:
        # The accepted identity freezes the full original plan as well. Live
        # preparation additionally supplies its independently reconstructed ref.
        plan_ref = record["plan"]
    p, q = r.policy(), policy()
    accepted = q["accepted_release"]
    r.validate_candidate(record, p, accepted["configuration_revision"], plan_ref)
    require(record["release_set_id"] == accepted["release_set_id"]
            and record["build"]["id"] == accepted["build_id"]
            and record["components"][0]["digest"] == accepted["manifest_digest"], "unaccepted_catalog_release")


def trust(cloud, artifact, occurrence):
    p = r.policy()
    require(re.fullmatch("projects/" + re.escape(p["project"]) + r"/occurrences/[A-Za-z0-9_-]+", occurrence or ""),
            "invalid_occurrence_reference")
    observed = r.decode(cloud.request("https://containeranalysis.googleapis.com/v1/" + occurrence))
    helper = r.attestation_helper()
    note = "projects/" + p["project"] + "/notes/secure-delivery-verification"
    key = "//cloudkms.googleapis.com/v1/projects/" + p["project"] + "/locations/us-central1/keyRings/secure-delivery-attestation/cryptoKeys/verification/cryptoKeyVersions/1"
    require(helper.inspect_occurrence([observed], artifact, key, note) == occurrence, "occurrence_mismatch")
    helper.validate_signature(observed, "projects/" + p["project"] + "/attestors/secure-delivery-verification", cloud.token)


def verify_application(record, occurrence, cloud):
    accepted = policy()["accepted_release"]
    with r.fetched(r.AML, r.REVISION) as source:
        plan = source.plan()
        ref = r.plan_reference(source, plan)
    candidate_policy(record, ref)
    result = r.verify(record, r.policy(), accepted["configuration_revision"], plan, ref, cloud)
    component = record["components"][0]
    trust(cloud, component["repository"] + "@" + component["digest"], occurrence)
    signer = cloud.build(r.policy(), accepted["signing_build_id"])
    uri = "gs://" + r.policy()["project"] + "-attestation-source/online-shop/catalog-v1/" + accepted["configuration_revision"] + "/" + accepted["build_id"] + "/candidate.json#" + accepted["candidate_generation"]
    expected = r.signing_request(r.policy(), accepted["configuration_revision"], uri, accepted["candidate_transport_sha256"])
    steps = [{k: v for k, v in step.items() if k not in ("status", "exitCode", "timing", "pullTiming")} for step in signer.get("steps", [])]
    name = r.build_url(r.policy(), accepted["signing_build_id"])
    numeric = name.replace("/" + r.policy()["project"] + "/", "/" + r.policy()["project_number"] + "/", 1)
    require(signer.get("status") == "SUCCESS"
            and signer.get("id") == accepted["signing_build_id"] and signer.get("projectId") == r.policy()["project"]
            and signer.get("name") in (name, numeric)
            and signer.get("serviceAccount") == r.policy()["signer"]
            and signer.get("source") == expected["source"]
            and signer.get("sourceProvenance", {}).get("resolvedGitSource") == expected["source"]["gitSource"]
            and signer.get("timeout") == expected["timeout"] and steps == expected["steps"]
            and all(step.get("status") == "SUCCESS" and step.get("exitCode", 0) == 0 for step in signer.get("steps", [])),
            "accepted_signing_build_unavailable")
    require(signer.get("options") in (expected["options"], {**expected["options"], "pool": {}, "workerRelease": "legacy"})
            and not any(signer.get(k) for k in ("images", "artifacts", "substitutions", "secrets", "availableSecrets", "dependencies", "gitConfig")),
            "accepted_signing_configuration_mismatch")
    transported = cloud.request("https://storage.googleapis.com/storage/v1/b/" + r.policy()["project"] + "-attestation-source/o/"
        + urllib.parse.quote(uri.split("-attestation-source/", 1)[1].split("#")[0], safe="")
        + "?alt=media&generation=" + accepted["candidate_generation"])
    require("sha256:" + r.sha(transported) == accepted["candidate_transport_sha256"] and r.decode(transported) == record,
            "accepted_candidate_transport_unavailable")
    return result


def verify_support(cloud, occurrence):
    """Only the reviewed Collector selection; this function never mirrors or signs."""
    c = support.policy()
    support.verify(c, cloud)
    trust(cloud, c["mirror_image"], occurrence)


def annotations(record, revision):
    return {"release.secure-delivery.dev/" + k: v for k, v in {
        "release-set-id": record["release_set_id"], "application-revision": record["source"]["revision"],
        "producing-configuration": record["configuration"]["revision"], "deployment-configuration": revision,
        "build-id": record["build"]["id"], "image-digest": record["components"][0]["digest"],
        "environment": "dev", "collector-config-sha256": r.sha((HERE / "collector.json").read_bytes().replace(b"\r\n", b"\n"))}.items()}


def render(record, revision):
    require(re.fullmatch(r.SHA, revision or ""), "invalid_deployment_revision")
    candidate_policy(record, record["plan"])
    p = r.policy()
    meta = annotations(record, revision)
    config_text = (HERE / "collector.json").read_text(encoding="utf-8").replace("\r\n", "\n")
    # Only reviewed constants, never candidate-supplied executable configuration.
    config_name = "catalog-collector-" + r.sha(config_text.encode())[:12]
    security = {"allowPrivilegeEscalation": False, "readOnlyRootFilesystem": True,
                "capabilities": {"drop": ["ALL"]}, "privileged": False}
    placement = {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"}
    app_env = {"PORT": "3550", "DISABLE_PROFILER": "1", "ONLINE_SHOP_TELEMETRY_ENABLED": "true",
               "ONLINE_SHOP_VERSION": r.REVISION, "ONLINE_SHOP_ENVIRONMENT": "dev",
               "OTEL_EXPORTER_OTLP_ENDPOINT": "http://catalog-collector.dev.svc.cluster.local:4317",
               "OTEL_EXPORTER_OTLP_PROTOCOL": "grpc", "OTEL_TRACES_EXPORTER": "otlp", "OTEL_METRICS_EXPORTER": "otlp",
               "OTEL_TRACES_SAMPLER_ARG": "0.1", "OTEL_METRIC_EXPORT_INTERVAL": "10000"}
    app = {"name": "catalog", "image": record["components"][0]["repository"] + "@" + record["components"][0]["digest"],
           "workingDir": "/src", "securityContext": security, "ports": [{"containerPort": 3550}],
           "env": [{"name": k, "value": v} for k, v in app_env.items()],
           "resources": {"requests": {"cpu": "100m", "memory": "64Mi"}, "limits": {"cpu": "200m", "memory": "128Mi"}},
           "startupProbe": {"grpc": {"port": 3550}, "periodSeconds": 2, "failureThreshold": 30},
           "readinessProbe": {"grpc": {"port": 3550}, "periodSeconds": 5},
           "livenessProbe": {"grpc": {"port": 3550}, "periodSeconds": 10, "failureThreshold": 3}}
    collector = {"name": "collector", "image": policy()["collector"]["mirror_image"],
        "args": ["--config=/etc/otelcol/config.json"], "securityContext": {**security, "runAsUser": 0, "runAsNonRoot": False},
        "resources": {"requests": {"cpu": "150m", "memory": "256Mi"}, "limits": {"cpu": "300m", "memory": "384Mi"}},
        "ports": [{"containerPort": 4317}, {"containerPort": 13133}],
        "volumeMounts": [{"name": "config", "mountPath": "/etc/otelcol", "readOnly": True},
                         {"name": "podlogs", "mountPath": "/var/log/pods", "readOnly": True},
                         {"name": "cursors", "mountPath": "/var/lib/otelcol"}],
        "startupProbe": {"httpGet": {"port": 13133, "path": "/"}, "periodSeconds": 2, "failureThreshold": 30},
        "readinessProbe": {"httpGet": {"port": 13133, "path": "/"}, "periodSeconds": 5},
        "livenessProbe": {"httpGet": {"port": 13133, "path": "/"}, "periodSeconds": 10}}
    def obj(kind, name, spec=None, **extra):
        x = {"apiVersion": "apps/v1" if kind in ("Deployment", "DaemonSet") else "v1", "kind": kind,
             "metadata": {"name": name, "namespace": "dev", "annotations": meta}}
        if spec is not None: x["spec"] = spec
        x.update(extra)
        return x
    app_spec = {"replicas": 1, "strategy": {"type": "RollingUpdate", "rollingUpdate": {"maxSurge": 1, "maxUnavailable": 0}},
        "selector": {"matchLabels": {"app": "productcatalogservice"}},
        "template": {"metadata": {"labels": {"app": "productcatalogservice"}, "annotations": meta}, "spec": {
            "serviceAccountName": "productcatalogservice", "automountServiceAccountToken": False,
            "nodeSelector": placement, "terminationGracePeriodSeconds": 30,
            "securityContext": {"runAsUser": 1000, "runAsGroup": 1000, "runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}}, "containers": [app]}}}
    collector_spec = {"updateStrategy": {"type": "RollingUpdate", "rollingUpdate": {"maxUnavailable": 1, "maxSurge": 0}},
        "selector": {"matchLabels": {"app": "catalog-collector"}},
        "template": {"metadata": {"labels": {"app": "catalog-collector"}, "annotations": meta}, "spec": {
            "serviceAccountName": "catalog-collector", "automountServiceAccountToken": False,
            "nodeSelector": {**placement, "iam.gke.io/gke-metadata-server-enabled": "true"}, "terminationGracePeriodSeconds": 30,
            "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}}, "containers": [collector],
            "volumes": [{"name": "config", "configMap": {"name": config_name}},
                        {"name": "podlogs", "hostPath": {"path": "/var/log/pods", "type": "Directory"}},
                        {"name": "cursors", "emptyDir": {"sizeLimit": "64Mi"}}]}}}
    return [obj("ServiceAccount", "productcatalogservice", automountServiceAccountToken=False),
            {"apiVersion": "v1", "kind": "ServiceAccount", "metadata": {"name": "catalog-collector", "namespace": "dev",
             "annotations": {"iam.gke.io/gcp-service-account": "catalog-telemetry@" + p["project"] + ".iam.gserviceaccount.com"}}},
            obj("ConfigMap", config_name, immutable=True, data={"config.json": config_text}),
            obj("Deployment", "productcatalogservice", app_spec), obj("DaemonSet", "catalog-collector", collector_spec),
            obj("Service", "productcatalogservice", {"type": "ClusterIP", "selector": {"app": "productcatalogservice"}, "ports": [{"name": "grpc", "port": 3550, "targetPort": 3550}]}),
            obj("Service", "catalog-collector", {"type": "ClusterIP", "selector": {"app": "catalog-collector"}, "ports": [{"name": "otlp-grpc", "port": 4317, "targetPort": 4317}]})]


def clouddeploy_labels(context):
    """Expected values come from reviewed API context, never checked labels."""
    p, q = r.policy(), policy()
    prefix = "projects/" + p["project"] + "/locations/" + p["region"]
    match = re.fullmatch(re.escape(prefix + "/deliveryPipelines/" + q["pipeline"] + "/releases/")
                         + r"([a-z][a-z0-9-]{0,62})", context.get("release_resource", ""))
    require(match is not None and context.get("target_resource") == prefix + "/targets/" + q["target"],
            "clouddeploy_context_mismatch")
    return {"app.kubernetes.io/managed-by": "google-cloud-deploy",
            "deploy.cloud.google.com/project-id": p["project"],
            "deploy.cloud.google.com/location": p["region"],
            "deploy.cloud.google.com/delivery-pipeline-id": q["pipeline"],
            "deploy.cloud.google.com/release-id": match[1],
            "deploy.cloud.google.com/target-id": q["target"]}


def inventory(documents, record, revision, *, artifact="prepared", release_context=None):
    # Exact object/Pod/config policy prevents hidden images, init/ephemeral
    # containers, bypass annotations, alternate commands or extra resources.
    expected = render(record, revision)
    require(artifact in ("prepared", "clouddeploy"), "invalid_manifest_artifact")
    if artifact == "clouddeploy":
        require(isinstance(release_context, dict), "clouddeploy_context_required")
        labels = clouddeploy_labels(release_context)
        # Add only the six documented labels at explicit resource/Pod-template
        # metadata paths. Selectors, annotations and all other fields stay exact.
        for document in expected:
            metadata = [document["metadata"]]
            if document["kind"] in ("Deployment", "DaemonSet"):
                metadata.append(document["spec"]["template"]["metadata"])
            for item in metadata:
                item["labels"] = {**item.get("labels", {}), **labels}
    require(r.canonical(documents) == r.canonical(expected), "rendered_policy_or_inventory_mismatch")
    return {"application": [record["components"][0]["repository"] + "@" + record["components"][0]["digest"]],
            "supporting": [policy()["collector"]["mirror_image"]]}


def prepare(record, app_occurrence, collector_occurrence, revision, output, cloud=None):
    reviewed(revision)
    cloud = cloud or r.Cloud()
    verification = verify_application(record, app_occurrence, cloud)
    verify_support(cloud, collector_occurrence)
    documents = render(record, revision)
    images = inventory(documents, record, revision)
    output = Path(output)
    require(not output.exists(), "output_directory_must_not_exist")
    target = output / "rendered/dev"
    target.mkdir(parents=True)
    manifest = json.dumps({"apiVersion": "v1", "kind": "List", "items": documents}, indent=2) + "\n"
    (target / "catalog.json").write_text(manifest, encoding="utf-8", newline="\n")
    (output / "skaffold.yaml").write_bytes((HERE / "skaffold.yaml").read_bytes().replace(b"\r\n", b"\n"))
    result = {"version": 1, "release_set_id": record["release_set_id"], "producing_configuration_revision": record["configuration"]["revision"],
        "deployment_configuration_revision": revision, "verification": verification, "inventory": images,
        "rendered_sha256": r.sha(manifest.encode()), "collector_configuration_sha256": annotations(record, revision)["release.secure-delivery.dev/collector-config-sha256"],
        "application_occurrence": app_occurrence, "collector_occurrence": collector_occurrence, "mutation_performed": False}
    (output / "preparation.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def evaluate(snapshot, record, revision, action, now=None, *, clouddeploy_release=None):
    """Fresh independently reviewed snapshot; eligibility never runs a rollout."""
    now = now or datetime.now(timezone.utc)
    candidate_policy(record, record["plan"])
    require(action in ("deploy", "promotion", "rollback"), "invalid_action")
    require(type(snapshot.get("version")) is int and snapshot["version"] == 1, "invalid_snapshot")
    checks = []
    def check(name, ok): checks.append({"id": name, "status": "PASS" if ok else "FAIL"})
    check("request_binding", snapshot.get("request") == {"release_set_id": record["release_set_id"], "deployment_revision": revision, "target": "dev", "action": action, "clouddeploy_release": clouddeploy_release})
    required = {"release": ("independently_verified", "application_signature_verified", "collector_publisher_verified", "collector_signature_verified"),
        "admission": ("cluster_enforced", "exact_attestor_required", "no_bypass"),
        "target": ("namespace_dev", "pipeline_catalog_dev", "snapshot_matches_current", "deployment_identity_matches", "workload_identity_ready", "log_exclusion_ready", "capacity_and_constraints_checked", "no_rollout_conflict"),
        "caller": ("rollout_create", "deployment_act_as"), "review": ("continue",),
        "clouddeploy": ("release_snapshot_matches_current",)}
    for section, fields in required.items():
        value = snapshot.get(section, {})
        try:
            observed = sample.utc(value.get("observed_at"))
            fresh = now - MAX_AGE <= observed <= now + timedelta(seconds=30) and bool(value.get("evidence_ref"))
        except (TypeError, ValueError): fresh = False
        check(section + "_fresh", fresh)
        check(section + "_binding", value.get("release_set_id") == record["release_set_id"] and value.get("deployment_revision") == revision)
        for field in fields: check(section + "_" + field, value.get(field) is True)
    for name in ("source", "rendered"):
        value = snapshot.get("artifacts", {}).get(name, {})
        try:
            fresh = now - MAX_AGE <= sample.utc(value.get("observed_at")) <= now + timedelta(seconds=30)
            protected = sample.utc(value.get("retention_expires_at")) >= now + MARGIN
        except (TypeError, ValueError): fresh = protected = False
        check(name + "_fresh_protected", fresh and protected and bool(value.get("evidence_ref")))
        check(name + "_bytes", value.get("available") is True and value.get("live_generation") is True
              and re.fullmatch(r"[0-9a-f]{64}", value.get("expected_sha256", "")) is not None
              and value.get("actual_sha256") == value.get("expected_sha256"))
        check(name + "_binding", value.get("release_set_id") == record["release_set_id"] and value.get("deployment_revision") == revision)
        check(name + "_release_annotation_hash", snapshot.get("release_annotations", {}).get(name + "_sha256") == value.get("expected_sha256"))
    context = snapshot.get("clouddeploy", {})
    check("clouddeploy_release_binding", isinstance(clouddeploy_release, str) and context.get("release_resource") == clouddeploy_release)
    try:
        inventory(snapshot.get("rendered_documents"), record, revision, artifact="clouddeploy", release_context=context)
        exact = True
    except (ValueError, KeyError, TypeError): exact = False
    check("exact_rendered_inventory", exact)
    check("dev_only_no_promotion", action != "promotion")
    if action == "rollback":
        prior = snapshot.get("rollback", {})
        check("rollback_previous_accepted", all(prior.get(k) is True for k in ("previously_accepted", "earlier_than_current", "different_from_current", "prior_dev_rollout_succeeded")))
        check("rollback_identity", prior.get("release_set_id") == record["release_set_id"])
    return {"decision": "READY" if all(x["status"] == "PASS" for x in checks) else "BLOCKED", "checks": checks,
            "release_set_id": record["release_set_id"], "target": "dev", "action": action,
            "deployment_configuration_revision": revision, "authorization": "separate_required", "mutation_performed": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "preflight"))
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--deployment-revision", required=True)
    parser.add_argument("--application-occurrence")
    parser.add_argument("--collector-occurrence")
    parser.add_argument("--output-dir")
    parser.add_argument("--snapshot")
    parser.add_argument("--clouddeploy-release", help="Intended full Cloud Deploy release resource; required for preflight")
    parser.add_argument("--intended-action", choices=("deploy", "promotion", "rollback"), default="deploy")
    args = parser.parse_args()
    try:
        record = r.read(args.candidate)
        with r.fetched(r.AML, r.REVISION) as source:
            candidate_policy(record, r.plan_reference(source, source.plan()))
        if args.action == "prepare":
            require(bool(args.output_dir), "output_required")
            result = prepare(record, args.application_occurrence, args.collector_occurrence, args.deployment_revision, args.output_dir)
            print(json.dumps({"status": "prepared", "release_set_id": result["release_set_id"], "mutation_performed": False}))
            return 0
        reviewed(args.deployment_revision)
        result = evaluate(r.read(args.snapshot), record, args.deployment_revision, args.intended_action,
                          clouddeploy_release=args.clouddeploy_release)
        print(json.dumps(result))
        return 0 if result["decision"] == "READY" else 3
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError):
        print(json.dumps({"status": "failed", "decision": "BLOCKED", "reason": "required_policy_or_evidence_check_failed", "mutation_performed": False}))
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
