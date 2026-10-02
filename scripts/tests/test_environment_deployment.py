"""Offline deployment boundary tests; subprocesses are never run against GCP."""
import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("deployment", ROOT / "deploy/deploy-release.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)
POLICY = deployment.load(ROOT / "deploy/environments.json")
DIGEST = "sha256:" + "a" * 64
RECORD = {
    "source_repository": POLICY["source_repository"], "commit_sha": "a" * 40,
    "build_id": "11111111-2222-3333-4444-555555555555",
    "build_service_account": POLICY["build_service_account"],
    "image_uri": POLICY["approved_registry"] + "/sample-service@" + DIGEST,
    "image_digest": DIGEST, "verification_status": "passed",
    "verification_timestamp": "2026-10-02T12:11:13Z",
    "trust_signal_ref": "projects/" + POLICY["project"] + "/occurrences/test-occurrence",
    "target_environment": "dev",
}


class DeploymentTest(unittest.TestCase):
    def invoke(self, record, environment="dev", reviewed=False, execute=False, runner=None):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "release.json"
            metadata.write_text(json.dumps(record), encoding="utf-8")
            output = Path(directory) / "out"
            arguments = ["deploy-release.py", "--metadata", str(metadata), "--environment", environment,
                         "--output-dir", str(output)]
            if reviewed:
                arguments.append("--reviewed")
            if execute:
                arguments.append("--execute")
            with patch("sys.argv", arguments), patch.object(deployment, "run", side_effect=runner or AssertionError("unexpected cloud command")) as commands, contextlib.redirect_stdout(io.StringIO()):
                code = deployment.main()
            result = json.loads((output / "deployment-result.json").read_text())
            manifest = (output / "sample-service.yaml").read_text() if (output / "sample-service.yaml").exists() else ""
            return code, result, manifest, commands.call_args_list

    def test_prepare_all_environments_preserves_release_without_cloud_calls(self):
        for environment in ("dev", "stage", "prod"):
            with self.subTest(environment=environment):
                code, result, manifest, calls = self.invoke({**RECORD, "target_environment": environment}, environment, environment != "dev")
                self.assertEqual(code, 0)
                self.assertEqual(result["deployment_status"], "prepared")
                self.assertEqual(result["artifact_identity"], RECORD["image_uri"])
                for field in ("commit_sha", "build_id", "build_service_account", "trust_signal_ref", "verification_timestamp"):
                    self.assertEqual(result[field], RECORD[field])
                    self.assertIn(RECORD[field], manifest)
                self.assertIn('namespace: "' + environment + '"', manifest)
                self.assertIn('value: "' + environment + '"', manifest)
                self.assertNotIn("REPLACE_WITH_", manifest)
                self.assertNotIn("break-glass", manifest)
                self.assertEqual(calls, [])

    def test_invalid_candidates_fail_before_cloud_calls_or_manifest(self):
        cases = [
            {"image_uri": POLICY["approved_registry"] + "/sample-service:latest"},
            {"image_digest": "sha256:" + "b" * 64},
            {"image_uri": "us-central1-docker.pkg.dev/foreign-project/repo/sample-service@" + DIGEST},
            {"verification_status": "failed"}, {"errors": ["failed"]},
            {"trust_signal_ref": ""}, {"trust_signal_ref": "projects/foreign-project/occurrences/id"},
            {"trust_signal_ref": "projects/" + POLICY["project"] + "/occurrences/SYNTHETIC-EXAMPLE"},
            {"build_service_account": POLICY["deployment_service_account"]},
            {"verification_timestamp": "not-a-timestampZ"}, {"target_environment": "prod"},
            {"commit_sha": "incomplete"},
        ]
        for changed in cases:
            with self.subTest(changed=changed):
                code, result, manifest, calls = self.invoke({**RECORD, **changed}, execute=True)
                self.assertEqual(code, 1)
                self.assertEqual(result["deployment_status"], "failed")
                self.assertEqual(manifest, "")
                self.assertEqual(calls, [])

    def test_review_required_for_stage_and_prod(self):
        for environment in ("stage", "prod"):
            code, result, _, calls = self.invoke({**RECORD, "target_environment": environment}, environment, execute=True)
            self.assertEqual(code, 1)
            self.assertEqual(result["error"], "environment_review_required")
            self.assertEqual(calls, [])

    def test_separate_authority_and_namespace_configuration(self):
        for mutation in ("authority", "namespace"):
            policy = copy.deepcopy(POLICY)
            if mutation == "authority":
                policy["deployment_service_account"] = policy["build_service_account"]
            else:
                policy["environments"]["dev"]["namespace"] = "prod"
            with self.assertRaises(ValueError):
                deployment.validate(RECORD, policy, "dev", False)
        with self.assertRaises(ValueError):
            deployment.validate(RECORD, POLICY, "other", False)

    def runner(self, failure=None):
        def run(command):
            if command[0] == "gcloud":
                self.assertIn("--impersonate-service-account=" + POLICY["deployment_service_account"], command)
                if "print-access-token" in command:
                    if failure == "impersonation":
                        raise ValueError("command_failed:gcloud:exit=1")
                    return "ephemeral-test-token"
                return json.dumps({"endpoint": "127.0.0.1", "binaryAuthorization": {"evaluationMode": "DISABLED" if failure == "enforcement" else "PROJECT_SINGLETON_POLICY_ENFORCE"}, "masterAuth": {"clusterCaCertificate": "Y2E="}})
            self.assertEqual(command[0], "kubectl")
            self.assertIn("--token=ephemeral-test-token", command)
            self.assertIn("--namespace=dev", command)
            if "namespace" in command:
                return json.dumps({"metadata": {"name": "prod" if failure == "namespace" else "dev"}})
            if "apply" in command:
                return "deployment configured; service configured"
            if "rollout" in command:
                if failure == "admission":
                    raise ValueError("command_failed:kubectl:exit=1")
                return "success"
            return json.dumps({"metadata": {"generation": 1, "uid": "test-uid"}, "spec": {"template": {"spec": {"containers": [{"image": "wrong" if failure == "digest" else RECORD["image_uri"]}]}}}, "status": {"observedGeneration": 1, "updatedReplicas": 1, "availableReplicas": 1}})
        return run

    def test_execute_requires_deploy_impersonation_and_successful_rollout(self):
        code, result, _, calls = self.invoke(RECORD, execute=True, runner=self.runner())
        self.assertEqual(code, 0)
        self.assertEqual(result["deployment_status"], "deployed")
        self.assertEqual(result["deployment_uid"], "test-uid")
        self.assertNotIn("ephemeral-test-token", json.dumps(result))
        self.assertTrue(any("apply" in call.args[0] for call in calls))

    def test_authority_enforcement_admission_and_digest_fail_closed(self):
        for failure in ("impersonation", "enforcement", "namespace", "admission", "digest"):
            with self.subTest(failure=failure):
                code, result, _, calls = self.invoke(RECORD, execute=True, runner=self.runner(failure))
                self.assertEqual(code, 1)
                self.assertEqual(result["deployment_status"], "failed")
                self.assertNotIn("deployed_at", result)
                if failure in ("impersonation", "enforcement", "namespace"):
                    self.assertFalse(any("apply" in call.args[0] for call in calls))

    def test_duplicate_json_fields_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            path.write_text('{"image_uri":"one","image_uri":"two"}')
            with self.assertRaises(ValueError):
                deployment.load(path)


if __name__ == "__main__":
    unittest.main()
