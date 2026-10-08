"""Offline checks for the documented review contract, not cloud evidence validation."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNBOOK = (ROOT / "docs/operator-runbook.md").read_text(encoding="utf-8")
CHECKPOINT = RUNBOOK.split("## Release review checkpoint\n", 1)[1].split("## Validation scenarios", 1)[0]


class ReleaseReviewCheckpointTest(unittest.TestCase):
    def test_four_evidence_groups_and_existing_procedures(self):
        for requirement in ("release identity", "trust evidence", "deployment state", "operational evidence",
                            "immutable image digest", "source repository/revision", "build ID and build identity",
                            "UID-owned Pods", "VERIFIED", "REQUIRE_ATTESTATION", "PROJECT_SINGLETON_POLICY_ENFORCE",
                            "observed generation", "sample timestamps", "Alerts section"):
            self.assertIn(requirement, CHECKPOINT)
        for anchor in ("runtime-release-correlation", "attestation-inspection", "runtime-validation",
                       "release-health-alert-review", "deployment-health-dashboard-review",
                       "application-log-inspection", "release-health-metric-inspection"):
            self.assertIn("](#" + anchor + ")", CHECKPOINT)

    def test_offline_decision_scenarios(self):
        rows = [line.split("|")[1:-1] for line in CHECKPOINT.splitlines() if line.startswith("| ")]
        scenarios = {row[0].strip(): row[1].strip() for row in rows[2:]}
        expected = {
            "Consistent identity, valid trust, settled deployment, sufficient fresh operational evidence": "continue",
            "Healthy workload, invalid signature or unexpected immutable digest": "reject",
            "Healthy workload, missing trust evidence": "hold",
            "Valid trust, stale or missing required operational evidence": "hold",
            "Valid trust, firing alert with unexplained cause": "hold",
            "Valid trust, confirmed release-specific deployment or operational failure": "reject",
            "Ambiguous rollout attribution or changing runtime identity": "hold",
            "Sparse non-health traffic, fresh readiness/gauges/probe evidence, bounded availability scope": "continue",
            "Sparse non-health traffic when application performance evidence is required": "hold",
        }
        self.assertEqual(scenarios, expected)
        self.assertEqual(set(scenarios.values()), {"continue", "hold", "reject"})

    def test_one_reasoned_record_and_mutation_boundary(self):
        record = CHECKPOINT.split("```text\n", 1)[1].split("```", 1)[0]
        self.assertEqual(len(re.findall(r"^decision:", record, re.M)), 1)
        for field in ("reviewed_at_utc", "observation_window_utc", "environment", "review_scope",
                      "identity_evidence", "trust_evidence", "deployment_evidence", "operational_evidence",
                      "missing_or_conflicting_evidence", "reason", "limitations_and_follow_up"):
            self.assertRegex(record, "(?m)^" + field + ": <[^>]+>")
        for rule in ("Healthy but untrusted must not continue", "Trusted but unhealthy must not continue automatically",
                     "Missing trust evidence means hold or reject, never continue",
                     "`continue` neither authorizes nor executes promotion", "does not execute rollback",
                     "A firing alert requires investigation", "no bypass path", "requires hold and a fresh review"):
            self.assertIn(rule, CHECKPOINT)
        self.assertNotRegex(CHECKPOINT, r"(?m)^\s*(?:gcloud .* (?:create|promote|approve|submit)|kubectl .*apply|terraform apply)")

    def test_public_safe_examples_and_canonical_links(self):
        self.assertNotRegex(CHECKPOINT, r"[\u0400-\u04ff]|gserviceaccount\.com|sre-platform-staging-[0-9]+|[A-Z]:\\")
        for document in ("docs/trusted-delivery.md", "docs/observability.md"):
            self.assertIn("operator-runbook.md#release-review-checkpoint", (ROOT / document).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
