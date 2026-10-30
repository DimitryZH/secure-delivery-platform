"""Catalog dev policy regressions. All cloud proof fakes are offline only."""
import copy
from datetime import datetime, timedelta, timezone
import importlib.util
import json
import io
from pathlib import Path
import tempfile
import os
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result
w = load("catalog_deployment", ROOT / "deploy/online-shop/workflow.py")
a = load("catalog_acceptance", ROOT / "deploy/online-shop/acceptance.py")
REV = "d" * 40
NOW = datetime(2026, 10, 30, 12, tzinfo=timezone.utc)
RELEASE_ID = "catalog-review-r1"
RESOURCE_PREFIX = "projects/" + w.r.policy()["project"] + "/locations/" + w.r.policy()["region"]
RELEASE_RESOURCE = RESOURCE_PREFIX + "/deliveryPipelines/catalog-dev/releases/" + RELEASE_ID
TARGET_RESOURCE = RESOURCE_PREFIX + "/targets/dev"
def stamp(minutes=0): return (NOW + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z")


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.policy = copy.deepcopy(w.policy())
        self.ref = {"sha256": "sha256:" + "a" * 64, "inputs_sha256": "sha256:" + "b" * 64,
                    "planner_sha256": "sha256:" + "c" * 64, "contract_sha256": "sha256:" + "e" * 64,
                    "uri": "git+" + w.r.AML + "@" + w.r.REVISION + "#" + w.r.WORKLOAD + "/build_plan.py"}
        accepted = self.policy["accepted_release"]
        self.record = w.r.candidate(w.r.policy(), accepted["configuration_revision"], self.ref, accepted["build_id"],
                                    accepted["manifest_digest"], "sha256:" + "f" * 64)
        self.policy["accepted_release"]["release_set_id"] = self.record["release_set_id"]
        self.patches = [patch.object(w, "policy", return_value=self.policy), patch.object(a.w, "policy", return_value=self.policy)]
        for item in self.patches: item.start(); self.addCleanup(item.stop)

    def clouddeploy_documents(self):
        # Explicit service contract fixture, independently of the implementation.
        labels = {"app.kubernetes.io/managed-by": "google-cloud-deploy",
                  "deploy.cloud.google.com/project-id": w.r.policy()["project"],
                  "deploy.cloud.google.com/location": w.r.policy()["region"],
                  "deploy.cloud.google.com/delivery-pipeline-id": "catalog-dev",
                  "deploy.cloud.google.com/release-id": RELEASE_ID,
                  "deploy.cloud.google.com/target-id": "dev"}
        docs = w.render(self.record, REV)
        for doc in docs:
            doc["metadata"].setdefault("labels", {}).update(labels)
            if doc["kind"] in ("Deployment", "DaemonSet"):
                doc["spec"]["template"]["metadata"]["labels"].update(labels)
        return docs

    def snapshot(self):
        common = {"observed_at": stamp(), "evidence_ref": "PRIVATE-READBACK", "release_set_id": self.record["release_set_id"], "deployment_revision": REV}
        sections = {"release": ["independently_verified", "application_signature_verified", "collector_publisher_verified", "collector_signature_verified"],
            "admission": ["cluster_enforced", "exact_attestor_required", "no_bypass"],
            "target": ["namespace_dev", "pipeline_catalog_dev", "snapshot_matches_current", "deployment_identity_matches", "workload_identity_ready", "log_exclusion_ready", "capacity_and_constraints_checked", "no_rollout_conflict"],
            "caller": ["rollout_create", "deployment_act_as"], "review": ["continue"],
            "clouddeploy": ["release_snapshot_matches_current"]}
        d = {"version": 1, "request": {"release_set_id": self.record["release_set_id"], "deployment_revision": REV, "target": "dev", "action": "deploy", "clouddeploy_release": RELEASE_RESOURCE},
             "rendered_documents": self.clouddeploy_documents(), "artifacts": {}, "release_annotations": {}}
        for section, fields in sections.items(): d[section] = {**common, **{k: True for k in fields}}
        d["clouddeploy"].update(release_resource=RELEASE_RESOURCE, target_resource=TARGET_RESOURCE)
        for name, sha in (("source", "a" * 64), ("rendered", "b" * 64)):
            d["artifacts"][name] = {**common, "expected_sha256": sha, "actual_sha256": sha, "available": True,
                                     "live_generation": True, "retention_expires_at": stamp(90)}
            d["release_annotations"][name + "_sha256"] = sha
        return d

    def decide(self, d, action="deploy"):
        return w.evaluate(d, self.record, REV, action, NOW, clouddeploy_release=RELEASE_RESOURCE)

    def test_clouddeploy_rendered_labels_and_prepared_manifest_are_distinct(self):
        prepared = w.render(self.record, REV)
        w.inventory(prepared, self.record, REV)
        self.assertEqual(self.decide(self.snapshot())["decision"], "READY")
        with self.assertRaisesRegex(ValueError, "inventory"):
            w.inventory(self.clouddeploy_documents(), self.record, REV)
        d = self.snapshot(); d["rendered_documents"] = prepared
        self.assertEqual(self.decide(d)["decision"], "BLOCKED")

    def test_wrong_or_unknown_generated_labels_fail_at_explicit_paths(self):
        for key in ("project-id", "location", "delivery-pipeline-id", "release-id", "target-id", "unknown-generated"):
            for path in ("resource", "template"):
                d = self.snapshot()
                metadata = d["rendered_documents"][3]["metadata"] if path == "resource" else d["rendered_documents"][3]["spec"]["template"]["metadata"]
                metadata["labels"]["deploy.cloud.google.com/" + key] = "wrong"
                with self.subTest(key=key, path=path):
                    self.assertEqual(self.decide(d)["decision"], "BLOCKED")
        d = self.snapshot(); d["rendered_documents"][0]["metadata"]["labels"]["app.kubernetes.io/managed-by"] = "other"
        self.assertEqual(self.decide(d)["decision"], "BLOCKED")

    def test_generated_labels_cannot_supply_their_own_release_context(self):
        for change in (lambda c: c.update(release_resource=RELEASE_RESOURCE.replace("/catalog-dev/", "/other/")),
                       lambda c: c.update(release_resource=RELEASE_RESOURCE.replace(w.r.policy()["project"], "other-project")),
                       lambda c: c.update(target_resource=TARGET_RESOURCE.replace("/dev", "/stage")),
                       lambda c: c.update(observed_at=stamp(-6))):
            d = self.snapshot(); change(d["clouddeploy"])
            self.assertEqual(self.decide(d)["decision"], "BLOCKED")
        d = self.snapshot()
        d["clouddeploy"]["release_resource"] = RELEASE_RESOURCE.replace(RELEASE_ID, "other-release")
        d["request"]["clouddeploy_release"] = d["clouddeploy"]["release_resource"]
        for doc in d["rendered_documents"]:
            doc["metadata"]["labels"]["deploy.cloud.google.com/release-id"] = "other-release"
            if doc["kind"] in ("Deployment", "DaemonSet"):
                doc["spec"]["template"]["metadata"]["labels"]["deploy.cloud.google.com/release-id"] = "other-release"
        # Even coherently forged labels/context do not change the intended resource.
        self.assertEqual(self.decide(d)["decision"], "BLOCKED")

    def test_generated_labels_do_not_hide_image_config_container_or_bypass_changes(self):
        mutations = [lambda d: d[3]["spec"]["template"]["spec"]["containers"][0].update(image="catalog:latest"),
                     lambda d: d[4]["spec"]["template"]["spec"]["containers"][0].update(image="collector:latest"),
                     lambda d: d[2]["data"].update({"config.json": "unreviewed"}),
                     lambda d: d[3]["spec"]["template"]["spec"].update(initContainers=[{"image": "hidden:tag"}]),
                     lambda d: d[3]["spec"]["template"]["spec"]["containers"][0]["securityContext"].update(privileged=True),
                     lambda d: d[3]["spec"]["template"]["metadata"]["annotations"].update({"alpha.image-policy.k8s.io/break-glass": "true"})]
        for mutation in mutations:
            d = self.snapshot(); mutation(d["rendered_documents"])
            self.assertEqual(self.decide(d)["decision"], "BLOCKED")

    def test_exact_separate_inventory_and_distinct_configuration_revisions(self):
        docs = w.render(self.record, REV)
        inventory = w.inventory(docs, self.record, REV)
        self.assertEqual(len(inventory["application"]), 1)
        self.assertEqual(len(inventory["supporting"]), 1)
        self.assertNotEqual(REV, self.record["configuration"]["revision"])
        self.assertEqual(self.decide(self.snapshot())["decision"], "READY")
        self.assertFalse(self.decide(self.snapshot())["mutation_performed"])

    def test_candidate_version_membership_identity_and_tags_fail_before_cloud(self):
        mutations = [lambda c: c.update(version=True), lambda c: c.update(version=1.0),
                     lambda c: c.update(components=[]), lambda c: c["components"].append(c["components"][0]),
                     lambda c: c["components"][0].update(repository="somewhere/image:tag"),
                     lambda c: c["components"][0].update(digest="latest"), lambda c: c["build"].update(id="0" * 36),
                     lambda c: c["configuration"].update(revision=REV)]
        for mutation in mutations:
            c = copy.deepcopy(self.record); mutation(c)
            with self.subTest(c=c), self.assertRaises((ValueError, KeyError, TypeError)):
                w.render(c, REV)

    def test_hidden_support_init_tag_substitution_and_manifest_changes_fail(self):
        mutations = [lambda d: d.append({"kind": "Pod", "spec": {"containers": [{"image": "evil:tag"}]}}),
                     lambda d: d[3]["spec"]["template"]["spec"].update(initContainers=[{"image": "evil:tag"}]),
                     lambda d: d[3]["spec"]["template"]["spec"]["containers"][0].update(image="catalog:latest"),
                     lambda d: d[4]["spec"]["template"]["spec"]["containers"][0].update(image="collector:latest"),
                     lambda d: d[2]["data"].update({"config.json": "unreviewed"}),
                     lambda d: d[3]["spec"].update(replicas=True),
                     lambda d: d[3]["spec"]["template"]["metadata"]["annotations"].update({"alpha.image-policy.k8s.io/break-glass": "true"})]
        for mutation in mutations:
            docs = copy.deepcopy(w.render(self.record, REV)); mutation(docs)
            with self.subTest(docs=docs), self.assertRaisesRegex(ValueError, "inventory"):
                w.inventory(docs, self.record, REV)

    def test_expired_unknown_wrong_target_retention_and_bound_hashes_block(self):
        for version in (True, 1.0):
            d = self.snapshot(); d["version"] = version
            with self.assertRaisesRegex(ValueError, "invalid_snapshot"): self.decide(d)
        mutations = [lambda d: d["request"].update(target="stage"), lambda d: d["release"].update(observed_at=stamp(-6)),
                     lambda d: d["admission"].update(cluster_enforced=False), lambda d: d["target"].pop("workload_identity_ready"),
                     lambda d: d["target"].update(capacity_and_constraints_checked=False),
                     lambda d: d["artifacts"]["source"].update(retention_expires_at=stamp(74)),
                     lambda d: d["artifacts"]["rendered"].update(actual_sha256="c" * 64),
                     lambda d: d["release_annotations"].update(source_sha256="f" * 64),
                     lambda d: d["rendered_documents"].pop()]
        for mutation in mutations:
            d = self.snapshot(); mutation(d)
            with self.subTest(d=d): self.assertEqual(self.decide(d)["decision"], "BLOCKED")

    def test_promotion_blocked_and_rollback_requires_previous_accepted_dev(self):
        d = self.snapshot(); d["request"]["action"] = "promotion"
        self.assertEqual(self.decide(d, "promotion")["decision"], "BLOCKED")
        d["request"]["action"] = "rollback"
        self.assertEqual(self.decide(d, "rollback")["decision"], "BLOCKED")
        d["rollback"] = {"release_set_id": self.record["release_set_id"], **{k: True for k in
            ("previously_accepted", "earlier_than_current", "different_from_current", "prior_dev_rollout_succeeded")}}
        self.assertEqual(self.decide(d, "rollback")["decision"], "READY")

    def test_failed_proof_or_unreviewed_code_never_writes_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "bundle"
            with patch.object(w, "reviewed", side_effect=ValueError("unreviewed")), patch.object(w.r, "Cloud") as cloud:
                with self.assertRaises(ValueError): w.prepare(self.record, "app", "collector", REV, dest)
                cloud.assert_not_called()
            with patch.object(w, "reviewed"), patch.object(w, "verify_application"), patch.object(w, "verify_support", side_effect=ValueError("untrusted")):
                with self.assertRaises(ValueError): w.prepare(self.record, "app", "collector", REV, dest, Mock())
            self.assertFalse(dest.exists())

    def test_prepare_only_local_outputs_no_deployment(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(w, "reviewed"), patch.object(w, "verify_application", return_value={"status": "passed"}), patch.object(w, "verify_support"):
            dest = Path(tmp) / "bundle"
            result = w.prepare(self.record, "app", "support", REV, dest, Mock())
            self.assertFalse(result["mutation_performed"])
            self.assertTrue((dest / "rendered/dev/catalog.json").is_file())
            self.assertEqual(w.r.sha((dest / "rendered/dev/catalog.json").read_bytes()), result["rendered_sha256"])
            self.assertFalse((dest / "rendered/stage").exists())

    def test_collector_policy_no_generic_sdk_log_export_or_credentials(self):
        config = w.r.read(w.HERE / "collector.json")
        self.assertEqual(config["service"]["pipelines"]["logs"]["receivers"], ["file_log/catalog"])
        self.assertEqual(config["service"]["pipelines"]["metrics"]["exporters"], ["googlecloud"])
        text = json.dumps(w.render(self.record, REV))
        for forbidden in ("hostNetwork", "hostPID", "GOOGLE_APPLICATION_CREDENTIALS", "service-account-key", "LoadBalancer"):
            self.assertNotIn(forbidden, text)
        collector = w.render(self.record, REV)[4]["spec"]["template"]["spec"]
        self.assertEqual(collector["nodeSelector"]["iam.gke.io/gke-metadata-server-enabled"], "true")

    def test_capacity_accounts_for_sidecar_init_overhead_and_constraints(self):
        node = {"metadata": {"name": "n", "labels": {"kubernetes.io/os": "linux", "kubernetes.io/arch": "amd64"}}, "spec": {},
                "status": {"allocatable": {"cpu": "2", "memory": "2Gi", "pods": "20"}, "conditions": [{"type": "Ready", "status": "True"}]}}
        pod = {"spec": {"nodeName": "n", "containers": [{"resources": {"requests": {"cpu": "100m", "memory": "32M"}}}],
                        "initContainers": [{"restartPolicy": "Always", "resources": {"requests": {"cpu": "50m"}}},
                                           {"resources": {"requests": {"cpu": "700m"}}}], "overhead": {"cpu": "10m"}}}
        self.assertEqual(a.pod_requests(pod, "cpu"), 760)
        self.assertTrue(a.capacity({"items": [node]}, {"items": [pod]})["capacity_ready"])
        node["spec"]["taints"] = [{"key": "restricted", "effect": "NoSchedule"}]
        self.assertFalse(a.capacity({"items": [node]}, {"items": [pod]})["capacity_ready"])

    def test_native_trace_link_required_not_only_json_trace_id(self):
        # A JSON trace_id without native LogEntry linkage must never pass.
        trace = "1" * 32
        snapshot = {"trace": {"traceId": trace, "spans": [{"spanId": "1", "name": "hipstershop.ProductCatalogService/ListProducts", "startTime": stamp()}]},
            "logs": {"entries": [{"jsonPayload": {"event": "request.completed", "operation": "/hipstershop.ProductCatalogService/ListProducts", "trace_id": trace}}]},
            "metrics": {"timeSeries": []}}
        with self.assertRaisesRegex(ValueError, "native_log_trace_link_missing"):
            a.signals(snapshot, self.record, stamp(-1))
        snapshot["trace"]["spans"] = []
        with self.assertRaisesRegex(ValueError, "empty_trace"): a.signals(snapshot, self.record, stamp(-1))

    def test_missing_cosign_fails_before_registry_or_attestation(self):
        cloud = Mock()
        with patch.object(w.shutil, "which", return_value=None), self.assertRaisesRegex(ValueError, "cosign_required"):
            w.verify_support(cloud, "support")
        cloud.request.assert_not_called()

    def test_accepted_signing_execution_and_original_transport_are_required(self):
        accepted = self.policy["accepted_release"]
        raw = w.r.canonical(self.record)
        accepted["candidate_transport_sha256"] = "sha256:" + w.r.sha(raw)
        uri = "gs://" + w.r.policy()["project"] + "-attestation-source/online-shop/catalog-v1/" + accepted["configuration_revision"] + "/" + accepted["build_id"] + "/candidate.json#" + accepted["candidate_generation"]
        signing = w.r.signing_request(w.r.policy(), accepted["configuration_revision"], uri, accepted["candidate_transport_sha256"])
        signing.update(id=accepted["signing_build_id"], projectId=w.r.policy()["project"],
                       name=w.r.build_url(w.r.policy(), accepted["signing_build_id"]), status="SUCCESS",
                       sourceProvenance={"resolvedGitSource": signing["source"]["gitSource"]})
        signing["steps"][0]["status"] = "SUCCESS"
        cloud = Mock(token="offline-only")
        cloud.build.return_value = signing; cloud.request.return_value = raw
        with patch.object(w.r, "fetched"), patch.object(w.r, "plan_reference", return_value=self.ref), \
                patch.object(w.r, "verify", return_value={"status": "passed"}), patch.object(w, "trust"):
            self.assertEqual(w.verify_application(self.record, "app", cloud)["status"], "passed")
            cloud.request.return_value = b"tampered"
            with self.assertRaisesRegex(ValueError, "transport_unavailable"):
                w.verify_application(self.record, "app", cloud)
            cloud.request.return_value = raw
            signing["id"] = "wrong-build"
            with self.assertRaisesRegex(ValueError, "signing_build_unavailable"):
                w.verify_application(self.record, "app", cloud)

    def runtime_pods(self, record=None):
        record = record or self.record
        docs = w.render(self.record, REV)
        pods = []
        for doc in (docs[3], docs[4]):
            template = copy.deepcopy(doc["spec"]["template"])
            template["metadata"]["namespace"] = "dev"
            template["spec"]["nodeName"] = "node-1"
            template["metadata"]["annotations"] = w.annotations(record, REV)
            container = template["spec"]["containers"][0]
            if container["name"] == "catalog":
                container["image"] = record["components"][0]["repository"] + "@" + record["components"][0]["digest"]
            template["status"] = {"containerStatuses": [{"name": container["name"], "ready": True,
                "imageID": "docker-pullable://" + container["image"]}]}
            pods.append(template)
        return {"items": pods}

    def test_runtime_rejects_unknown_running_digest_and_missing_members(self):
        pods = self.runtime_pods()["items"]
        self.assertEqual(a.runtime({"items": pods}, self.record, REV)["runtime"], "passed")
        pods[0]["status"]["containerStatuses"][0]["imageID"] = "containerd://sha256:" + "0" * 64
        with self.assertRaisesRegex(ValueError, "running_digest_unproven"): a.runtime({"items": pods}, self.record, REV)
        with self.assertRaisesRegex(ValueError, "missing_runtime_member"): a.runtime({"items": []}, self.record, REV)

    @unittest.skipUnless(os.environ.get("SDP_COLLECTOR_EXECUTABLE"), "native Collector optional integration")
    def test_real_collector_parses_json_trace_span_flags_without_cloud_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            logs = directory / "catalog.log"
            trace, span = "1" * 32, "2" * 16
            logs.write_text(stamp() + " stdout F " + json.dumps({"timestamp": stamp(), "severity": "INFO", "trace_id": trace,
                "span_id": span, "trace_flags": 1, "event": "request.completed"}) + "\n", encoding="utf-8")
            config = w.r.read(w.HERE / "collector.json")
            receiver = config["receivers"]["file_log/catalog"]
            receiver.update(include=[str(logs)], start_at="beginning")
            # CRI parsing is real; Linux filepath metadata/permissions require GKE.
            receiver["operators"][0]["add_metadata_from_filepath"] = False
            config["receivers"] = {"file_log/catalog": receiver}
            config["exporters"] = {"debug": {"verbosity": "detailed"}}
            config["extensions"] = {"file_storage": {"directory": str(directory / "cursors"), "create_directory": True}}
            config["service"] = {"extensions": ["file_storage"], "pipelines": {"logs": {
                "receivers": ["file_log/catalog"], "processors": ["resource/catalog"], "exporters": ["debug"]}}}
            path = directory / "config.json"; path.write_text(json.dumps(config), encoding="utf-8")
            child = subprocess.Popen([os.environ["SDP_COLLECTOR_EXECUTABLE"], "--config=" + str(path)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try: stdout, stderr = child.communicate(timeout=4)
            except subprocess.TimeoutExpired:
                child.kill(); stdout, stderr = child.communicate()
            text = (stdout + stderr).decode(errors="replace")
            self.assertRegex(text, r"Trace ID:\s+" + trace)
            self.assertRegex(text, r"Span ID:\s+" + span)
            self.assertRegex(text, r"Flags:\s+1")
            self.assertNotIn("failed to process", text.lower())

    def signal_snapshot(self, record=None):
        record = record or self.record
        trace = "1" * 32; span = "0000000000000001"
        labels = {"service.name": "productcatalogservice", "service.version": w.r.REVISION,
                  "deployment.environment.name": "dev", "release_set_id": record["release_set_id"],
                  "component_digest": record["components"][0]["digest"]}
        metric_labels = {k.replace(".", "_"): v for k, v in labels.items()}
        metric_labels.update(kind="server", operation="/hipstershop.ProductCatalogService/ListProducts")
        snapshot = {"trace": {"traceId": trace, "spans": [{"spanId": "1", "name": "hipstershop.ProductCatalogService/ListProducts", "startTime": stamp()}]},
            "logs": {"entries": [{"trace": "projects/" + w.r.policy()["project"] + "/traces/" + trace, "spanId": span,
                "timestamp": stamp(), "logName": "projects/" + w.r.policy()["project"] + "/logs/online-shop%2Fcatalog", "labels": labels,
                "resource": {"type": "k8s_container", "labels": {"namespace_name": "dev", "cluster_name": "secure-delivery-platform", "container_name": "catalog"}},
                "jsonPayload": {"event": "request.completed", "operation": "/hipstershop.ProductCatalogService/ListProducts", "trace_id": trace, "span_id": span}}]},
            "metrics": {"timeSeries": [{"metric": {"type": "workload.googleapis.com/online_shop.transport.requests", "labels": metric_labels},
                "points": [{"interval": {"endTime": stamp()}, "value": {"int64Value": "3"}}]}]}}
        return snapshot

    def test_actual_signal_shapes_require_nonzero_metrics_and_linked_attribution(self):
        snapshot = self.signal_snapshot()
        with patch.object(a, "datetime") as clock:
            clock.now.return_value = NOW
            self.assertTrue(a.signals(snapshot, self.record, stamp(-1))["native_trace_linkage"])
            snapshot["metrics"]["timeSeries"] = []
            with self.assertRaisesRegex(ValueError, "metrics_missing"): a.signals(snapshot, self.record, stamp(-1))

    def test_acceptance_rejects_changed_digest_even_with_matching_pods_and_signals(self):
        record = copy.deepcopy(self.record)
        record["components"][0]["digest"] = "sha256:" + "0" * 64
        for recompute in (False, True):
            if recompute:
                record["release_set_id"] = w.r.fingerprint({k: v for k, v in record.items() if k != "release_set_id"})
            expected = "unaccepted_catalog_release" if recompute else "candidate_identity_mismatch"
            with self.subTest(recomputed=recompute):
                with self.assertRaisesRegex(ValueError, expected): a.runtime(self.runtime_pods(record), record, REV)
                with patch.object(a, "datetime") as clock:
                    clock.now.return_value = NOW
                    with self.assertRaisesRegex(ValueError, expected): a.signals(self.signal_snapshot(record), record, stamp(-1))

    def test_acceptance_candidate_guard_precedes_all_evidence_processing(self):
        class EvidenceMustNotBeRead:
            def __getitem__(self, key): raise AssertionError("evidence processed before guard")
        mutations = [lambda c: c.update(version=True), lambda c: c.update(version=1.0),
                     lambda c: c.update(plan=None), lambda c: c.update(components=[]),
                     lambda c: c.update(profile="other"), lambda c: c["source"].update(revision=REV),
                     lambda c: c["build"].update(id="11111111-2222-3333-4444-555555555555"),
                     lambda c: c.update(unexpected=True)]
        for mutation in mutations:
            record = copy.deepcopy(self.record); mutation(record)
            for recompute in (False, True):
                if recompute: record["release_set_id"] = w.r.fingerprint({k: v for k, v in record.items() if k != "release_set_id"})
                with self.subTest(record=record), self.assertRaises(ValueError): a.runtime(EvidenceMustNotBeRead(), record, REV)
                with self.subTest(record=record), self.assertRaises(ValueError): a.signals(EvidenceMustNotBeRead(), record, "not-a-time")
        for record in (None, [], True):
            with self.assertRaises(ValueError): a.runtime(EvidenceMustNotBeRead(), record, REV)
            with self.assertRaises(ValueError): a.signals(EvidenceMustNotBeRead(), record, "not-a-time")

    def test_acceptance_cli_rejects_candidate_before_reading_snapshot_file(self):
        record = copy.deepcopy(self.record); record["version"] = True
        original_read = a.w.r.read
        def read(path):
            if path == "candidate.json": return record
            if path == "evidence.json": raise AssertionError("snapshot read before candidate guard")
            return original_read(path)
        for check in ("runtime", "signals"):
            args = ["acceptance.py", check, "--candidate", "candidate.json", "--snapshot", "evidence.json"]
            with self.subTest(check=check), patch.object(a.w.r, "read", side_effect=read), \
                    patch.object(sys, "argv", args), patch("sys.stdout", new_callable=io.StringIO):
                self.assertEqual(a.main(), 3)


if __name__ == "__main__": unittest.main()
