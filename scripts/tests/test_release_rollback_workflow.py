"""Offline documentation-contract scenarios; no deployment or rollback is executed."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEXT = (ROOT / "docs/operator-runbook.md").read_text(encoding="utf-8").split(
    "## Manual release rejection and rollback\n", 1)[1].split("## Release review checkpoint", 1)[0]


class ReleaseRollbackWorkflowTest(unittest.TestCase):
    def test_rejection_record_and_no_automatic_mutation(self):
        for field in ("rejected_at_utc", "environment", "immutable_digest", "reason_and_evidence",
                      "progression_stop", "rollback_need", "rollback_need_reason"):
            self.assertRegex(TEXT, "(?m)^" + field + ": <|(?m:^" + field + ": sha256:<)")
        for rule in ("decision: reject", "required_deferred_not_applicable", "Stop issuing further promotions and approvals",
                     "does not cancel queued/in-progress jobs", "Do not grant a pending approval",
                     "Do not retry/redeploy, rebuild, resign, modify trust"):
            self.assertIn(rule, TEXT)

    def test_candidate_trust_material_and_protection_gates(self):
        for requirement in ("acceptance evidence", "source revision", "producing build ID/identity",
                            "retained passed trusted verification output", "VERIFIED signature", "current",
                            "attestor/note/key", "75-minute", "recorded generation", "source SHA-256",
                            "readability by the existing deploy execution authority", "expired protection",
                            "soft-deleted bytes", "data/schema incompatibility"):
            self.assertIn(requirement, TEXT)
        for boundary in ("never rebuild historical source, retag, substitute", "Do not silently recover, upload",
                         "Missing or invalid trust blocks rollback"):
            self.assertIn(boundary, TEXT)

    def test_explicit_existing_release_new_rollout_and_separate_approval(self):
        command = TEXT.split("```sh\n", 1)[1].split("```", 1)[0]
        self.assertEqual(command.count("gcloud deploy targets rollback"), 1)
        for flag in ("--project=<PROJECT_ID>", "--region=<REGION>", "--delivery-pipeline=sample-service",
                     "--release=<PREVIOUS_ACCEPTED_RELEASE>", "--rollout-id=<NEW_ROLLBACK_ROLLOUT_ID>"):
            self.assertIn(flag, command)
        self.assertNotRegex(command, r"kubectl|--images|--override|builds|releases create")
        for rule in ("separate explicit authorization", "PENDING_APPROVAL/NEEDS_APPROVAL",
                     "Do not assume historical approval authorizes the new rollout",
                     "no new release/source upload/application build", "direct kubectl mutation",
                     "command exit success alone is insufficient", "Compare every unrelated environment"):
            self.assertIn(rule, TEXT)

    def test_rollback_caller_permission_is_separate_and_fail_closed(self):
        for requirement in ("exact rollback caller", "effective `clouddeploy.rollouts.rollback` permission",
                            "intended delivery pipeline", "IAM conditions and deny policies",
                            "Cloud Deploy Job Runner (`roles/clouddeploy.jobRunner`)",
                            "separate from rollback-caller authority",
                            "If the permission is absent or cannot be verified",
                            "blocked pending separately reviewed IAM authorization/change",
                            "Do not grant or modify IAM, add permissions automatically",
                            "not rollback execution authorization"):
            self.assertIn(requirement, TEXT)
        self.assertIn("rollback_caller_permission: <CALLER_SCOPE_TIMESTAMP_AND_clouddeploy.rollouts.rollback_EVIDENCE_OR_BLOCKED>", TEXT)

    def test_offline_rejection_and_rollback_scenarios(self):
        table = TEXT.split("### Offline rejection and rollback scenarios", 1)[1]
        rows = [line.split("|")[1:-1] for line in table.splitlines() if line.startswith("| ")]
        actual = {row[0].strip(): row[1].strip() for row in rows[2:]}
        self.assertEqual(actual, {
            "Reject before deployment; rollback not applicable": "progression stopped",
            "Reject deployed release; accepted immutable candidate and all gates pass": "authorization required",
            "Candidate image or required source/render material unavailable": "rollback blocked",
            "Source/render bytes readable but retention expired or margin insufficient": "rollback blocked",
            "Candidate trust missing or invalid": "rollback blocked",
            "Candidate identified only by mutable tag": "rollback blocked",
            "Concurrent rollout or target/authority mismatch": "rollback blocked",
        })

    def test_post_validation_and_public_safe_contract(self):
        for required in ("actual imageID", "positive desired replicas", "Ready owned Pods",
                         "Recheck valid attestation and enforced Binary Authorization", "alert review",
                         "deployment health dashboard review", "release review outcome"):
            self.assertIn(required, TEXT)
        self.assertNotRegex(TEXT, r"[\u0400-\u04ff]|gserviceaccount\.com|sre-platform-staging-[0-9]+|[A-Z]:\\")
        for file in ("docs/trusted-delivery.md", "docs/observability.md"):
            self.assertIn("operator-runbook.md#manual-release-rejection-and-rollback",
                          (ROOT / file).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
