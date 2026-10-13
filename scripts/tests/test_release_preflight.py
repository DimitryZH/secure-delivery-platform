"""Offline release decision scenarios; no cloud access or mutation."""

from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy/clouddeploy/release-preflight.py"
SPEC = importlib.util.spec_from_file_location("release_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(preflight)
POLICY = preflight.deployment.load(ROOT / "deploy/environments.json")
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)
RELEASE = "release-example"
DIGEST = "sha256:" + "a" * 64
SHA = "b" * 64
BUILD = "12345678-1234-1234-1234-123456789abc"


def stamp(offset=0):
    return (NOW + timedelta(minutes=offset)).isoformat().replace("+00:00", "Z")


def evidence(action="promotion", target="stage"):
    metadata = {
        "source_repository": POLICY["source_repository"],
        "commit_sha": "c" * 40,
        "build_id": BUILD,
        "build_service_account": POLICY["build_service_account"],
        "image_uri": POLICY["approved_registry"] + "/sample-service@" + DIGEST,
        "image_digest": DIGEST,
        "verification_status": "passed",
        "verification_timestamp": stamp(-60),
        "errors": [],
        "trust_signal_ref": "projects/" + POLICY["project"] + "/occurrences/EXAMPLE",
    }
    common = {"observed_at": stamp(), "evidence_ref": "PRIVATE-READBACK-REFERENCE"}
    artifact = {**common, "release": RELEASE, "available": True,
                "live_generation": True, "expected_sha256": SHA, "actual_sha256": SHA,
                "retention_expires_at": stamp(90)}
    return {
        "schema_version": 1,
        "request": {"release": RELEASE, "target": target, "action": action, "digest": DIGEST},
        "identity": {**common, "release": RELEASE, "digest": DIGEST,
                     "metadata": metadata, "release_annotations_match": True,
                     "render_succeeded": True, "source_archive_sha256": SHA},
        "build": {**common, "build_id": BUILD, "digest": DIGEST, "succeeded": True,
                  "source_and_identity_match": True, "image_available": True},
        "verification": {**common, "digest": DIGEST, "build_id": BUILD,
                         "trusted_result_retained": True, "passed": True},
        "attestation": {**common, "digest": DIGEST,
                        "occurrence": metadata["trust_signal_ref"],
                        "signature_verified": True, "attestor_note_key_match": True},
        "admission": {**common, "cluster_enforced": True,
                      "policy_requires_attestor": True, "no_bypass": True},
        "artifacts": {"source": artifact.copy(),
                      "rendered": {**artifact, "target": target, "digest": DIGEST}},
        "target_state": {**common, "target": target,
                         "namespace": target,
                         "deployment_authority": POLICY["deployment_service_account"],
                         "approval_required": POLICY["environments"][target]["review_required"],
                         "release_snapshot_matches_current": True,
                         "deployment_authority_matches": True,
                         "approval_gate_matches_policy": True,
                         "namespace_and_digest_match": True,
                         "target_render_succeeded": True},
        "rollouts": {**common, "no_active_or_queued_conflict": True,
                     "successful_prior_target": "dev" if target == "stage" else "stage",
                     "successful_prior_release": RELEASE,
                     "successful_prior_digest": DIGEST,
                     "prior_rollout_and_job_succeeded": True,
                     "no_target_rollout_for_release": True,
                     "prior_target_rollout_and_job_succeeded": True,
                     "prior_target_release": RELEASE, "prior_target_digest": DIGEST,
                     "previously_accepted": True, "earlier_than_current": True,
                     "different_from_current": True},
        "caller": {**common, "permission": "clouddeploy.rollouts.create" if action == "promotion"
                   else "clouddeploy.rollouts.rollback", "effective_permission": True,
                   "rollout_create_permission": True,
                   "deployment_act_as_permission": True},
        "operations": {**common, "release": RELEASE, "digest": DIGEST,
                       "reviewed_target": "dev" if action == "promotion" else target,
                       "review_complete": True, "decision": "continue",
                       "health_evidence_sufficient": True, "runtime_identity_stable": True},
    }


class ReleasePreflightTests(unittest.TestCase):
    def decide(self, record, action="promotion", target="stage"):
        return preflight.evaluate(record, RELEASE, target, action, DIGEST, NOW)

    def assert_issue(self, result, code):
        self.assertIn(code, {item["code"] for item in result["issues"]})

    def test_promotion_ready_is_not_authorization(self):
        result = self.decide(evidence())
        self.assertEqual(result["decision"], "READY")
        self.assertEqual(result["issues"], [])
        self.assertEqual(result["authorization"], "separate_required")
        self.assertFalse(result["cloud_action_executed"])

    def test_rollback_ready_requires_explicit_prior_acceptance(self):
        record = evidence("rollback")
        self.assertEqual(self.decide(record, "rollback")["decision"], "READY")
        record["rollouts"]["previously_accepted"] = False
        result = self.decide(record, "rollback")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "rollback_release_not_accepted")

    def test_missing_or_stale_evidence_holds(self):
        record = evidence()
        del record["verification"]["trusted_result_retained"]
        record["operations"]["observed_at"] = stamp(-6)
        result = self.decide(record)
        self.assertEqual(result["decision"], "HOLD")
        self.assert_issue(result, "trusted_verification_missing")
        self.assert_issue(result, "operations_observation_expired")

    def test_expired_protection_and_conflict_block(self):
        record = evidence()
        record["artifacts"]["source"]["retention_expires_at"] = stamp(74)
        record["rollouts"]["no_active_or_queued_conflict"] = False
        result = self.decide(record)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "source_retention_insufficient")
        self.assert_issue(result, "conflicting_rollout")

    def test_digest_mismatch_and_invalid_attestation_block(self):
        record = evidence()
        record["identity"]["metadata"]["image_digest"] = "sha256:" + "d" * 64
        record["attestation"]["signature_verified"] = False
        result = self.decide(record)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "metadata_digest_mismatch")
        self.assert_issue(result, "attestation_invalid")

    def test_unavailable_render_and_admission_mismatch_block(self):
        record = evidence()
        record["artifacts"]["rendered"]["available"] = False
        record["admission"]["policy_requires_attestor"] = False
        record["target_state"]["approval_required"] = False
        result = self.decide(record)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "rendered_artifact_unavailable")
        self.assert_issue(result, "admission_policy_incompatible")
        self.assert_issue(result, "target_approval_requirement_mismatch")

    def test_promotion_requires_prior_target_and_review(self):
        record = evidence()
        record["rollouts"]["successful_prior_target"] = "prod"
        result = self.decide(record)
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "prior_target_mismatch")

    def test_rollback_requires_earlier_different_release_and_authority(self):
        record = evidence("rollback")
        record["rollouts"]["earlier_than_current"] = False
        record["rollouts"]["different_from_current"] = False
        record["caller"]["effective_permission"] = False
        record["caller"]["deployment_act_as_permission"] = False
        result = self.decide(record, "rollback")
        self.assertEqual(result["decision"], "BLOCKED")
        self.assert_issue(result, "rollback_not_earlier_release")
        self.assert_issue(result, "caller_not_authorized")
        self.assert_issue(result, "caller_cannot_act_as_deployment_identity")

    def test_malformed_input_exits_blocked_without_identifiers(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "evidence.json"
            path.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--release", RELEASE, "--target", "stage",
                 "--action", "promotion", "--digest", DIGEST,
                 "--evidence", str(path), "--format", "json"],
                check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 3)
        self.assertEqual(json.loads(completed.stdout)["decision"], "BLOCKED")
        self.assertNotIn(POLICY["project"], completed.stdout)

    def test_cli_emits_ready_as_text_and_json_without_cloud_action(self):
        record = evidence()
        current = datetime.now(timezone.utc)
        observed = current.isoformat().replace("+00:00", "Z")
        expires = (current + timedelta(minutes=90)).isoformat().replace("+00:00", "Z")
        for name in ("identity", "build", "verification", "attestation", "admission",
                     "target_state", "rollouts", "caller", "operations"):
            record[name]["observed_at"] = observed
        for name in ("source", "rendered"):
            record["artifacts"][name]["observed_at"] = observed
            record["artifacts"][name]["retention_expires_at"] = expires
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory) / "evidence.json"
            path.write_text(json.dumps(record), encoding="utf-8")
            command = [sys.executable, str(SCRIPT), "--release", RELEASE,
                       "--target", "stage", "--action", "promotion", "--digest", DIGEST,
                       "--evidence", str(path)]
            human = subprocess.run(command, check=False, capture_output=True, text=True)
            machine = subprocess.run(command + ["--format", "json"],
                                     check=False, capture_output=True, text=True)
        self.assertEqual(human.returncode, 0)
        self.assertIn("READY", human.stdout)
        self.assertIn("Separate authorization is required", human.stdout)
        self.assertEqual(machine.returncode, 0)
        self.assertEqual(json.loads(machine.stdout)["decision"], "READY")
        self.assertNotIn(POLICY["project"], human.stdout + machine.stdout)


if __name__ == "__main__":
    unittest.main()
