"""Reviewed target activation and stage boundaries, entirely offline."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from release_fixtures import accepted_policy

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


r = load("binding_release", "cloudbuild/online-shop/release.py")
w = load("binding_workflow", "deploy/online-shop/workflow.py")
c = load("binding_complete", "cloudbuild/online-shop/complete.py")


class BindingTests(unittest.TestCase):
    def test_binding_schema_and_bootstrap_do_not_need_accepted_evidence(self):
        b, p = r.binding(), r.policy()
        self.assertEqual((b["project"], b["project_number"]), ("sdp-gcp", "738317279206"))
        self.assertNotEqual(p["producer"], p["signer"])
        self.assertIsNone(w.policy()["accepted_release"])
        self.assertIsNone(w.policy()["collector_occurrence"])
        request = r.build_request(p, "c" * 40, {"components": [{"inputs": []}]})
        self.assertEqual(request["serviceAccount"], p["producer"])
        schema = r.read(ROOT / "cloudbuild/online-shop/candidate-v1.schema.json")
        self.assertEqual(schema["properties"]["build"]["properties"]["producer"]["const"], p["producer"])
        full = r.read(ROOT / "cloudbuild/online-shop/complete-candidate-v1.schema.json")
        self.assertEqual(full["$defs"]["build"]["properties"]["producer"]["const"], p["producer"])
        for row in full["properties"]["components"]["prefixItems"][:-1]:
            item = row["allOf"][1]["properties"]
            self.assertEqual(item["repository"]["const"], p["registry"] + "/online-shop-" + item["id"]["const"])
        for path in ("deploy/environments.json", "deploy/release-binding.json", "cloudbuild/online-shop/candidate-v1.schema.json"):
            self.assertIn(path, r.TRUSTED_FILES)

    def test_mixed_binding_and_environment_rejected(self):
        original = r.read
        for field in ("registry", "producer", "signer", "deployer", "key_version", "attestor", "note", "candidate_bucket", "clouddeploy_bucket"):
            b = r.binding(); b[field] = b[field].replace("sdp-gcp", "historical-project")
            with self.subTest(field=field), patch.object(r, "read", side_effect=lambda path: b if Path(path).name == "release-binding.json" else original(path)):
                with self.assertRaisesRegex(ValueError, "mixed_release_binding"): r.policy()
        for field, value in (("project_number", "465837787797"), ("release_binding", "old-binding"),
                             ("cluster", "other-cluster"), ("location", "us-east1-b"), ("build_service_account", "other@example.invalid"), ("endpoint_enabled", None)):
            env = original(ROOT / "deploy/environments.json"); env[field] = value
            with self.subTest(field=field), patch.object(r, "read", side_effect=lambda path: env if Path(path).name == "environments.json" else original(path)):
                with self.assertRaises(ValueError): r.policy()

    def test_pending_and_foreign_acceptance_stop_before_cloud(self):
        cloud = Mock()
        with self.assertRaisesRegex(ValueError, "accepted_catalog_pending"): c.catalog_candidate(cloud)
        cloud.request.assert_not_called()
        with self.assertRaisesRegex(ValueError, "accepted_catalog_pending"):
            c.build_request("frontend", "c" * 40, {"components": [{"id": "frontend"}]})
        with self.assertRaisesRegex(ValueError, "accepted_collector_pending"): w.collector_occurrence()
        for field, value in (("project", "historical-project"), ("binding", "old-binding"), ("build_id", None),
                             ("candidate_generation", None), ("readback_generation", ""), ("readback_generation", None), ("candidate_transport_sha256", None),
                             ("signing_build_id", None), ("occurrence", "projects/historical-project/occurrences/old")):
            q = accepted_policy(c.r); q["accepted_release"][field] = value
            with self.subTest(field=field), patch.object(c.legacy, "policy", return_value=q):
                with self.assertRaises(ValueError): c.catalog_candidate(cloud)
            cloud.request.assert_not_called()

    def test_historical_candidate_cannot_be_relabelled_with_new_identity(self):
        ref = {"sha256": "sha256:" + "a" * 64}
        record = r.candidate(r.policy(), "c" * 40, ref, "11111111-2222-3333-4444-555555555555", "sha256:" + "b" * 64, "sha256:" + "d" * 64)
        r.validate_candidate(record, r.policy(), "c" * 40, ref)
        for field in ("producer", "name", "repository"):
            bad = copy.deepcopy(record)
            row = bad["components"][0] if field == "repository" else bad["build"]
            row[field] = row[field].replace("sdp-gcp", "sre-platform-staging-507220")
            bad["release_set_id"] = r.fingerprint({k: v for k, v in bad.items() if k != "release_set_id"})
            with self.subTest(field=field), self.assertRaises(ValueError): r.validate_candidate(bad, r.policy(), "c" * 40, ref)

    def test_collector_exporter_and_local_auth_fail_closed(self):
        q = w.collector_configuration()
        self.assertEqual(q["exporters"]["googlecloud"]["project"], r.policy()["project"])
        q["exporters"]["googlecloud"]["project"] = "foreign-project"
        original = w.r.read
        with patch.object(w.r, "read", side_effect=lambda path: q if Path(path).name == "collector.json" else original(path)):
            with self.assertRaisesRegex(ValueError, "collector_export_binding_mismatch"): w.collector_configuration()
        with patch.dict(os.environ, {}, clear=True), patch.object(r.shutil, "which", return_value="gcloud"), patch.object(r, "command") as command:
            with self.assertRaisesRegex(ValueError, "explicit_cloud_identity_required"): r.Cloud()
            command.assert_not_called()


if __name__ == "__main__":
    unittest.main()
