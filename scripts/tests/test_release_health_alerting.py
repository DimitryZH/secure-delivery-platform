"""Offline policy-contract checks; live PromQL parsing requires read-only API validation."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "terraform/foundation/alert-policy.tf.json").read_text(encoding="utf-8"))
LOCALS = CONFIG["locals"]
POLICY = CONFIG["resource"]["google_monitoring_alert_policy"]["sample_service_availability"]
GROUP = "project_id, location, cluster, namespace, deployment"


class ReleaseHealthAlertingTest(unittest.TestCase):
    def test_one_policy_without_resource_expansion(self):
        self.assertEqual(set(CONFIG), {"locals", "resource"})
        self.assertEqual(set(CONFIG["resource"]), {"google_monitoring_alert_policy"})
        self.assertEqual(set(CONFIG["resource"]["google_monitoring_alert_policy"]), {"sample_service_availability"})
        self.assertEqual(POLICY["project"], "${var.project_id}")
        self.assertEqual(POLICY["depends_on"], ["google_project_service.required"])
        self.assertTrue(POLICY["enabled"])
        self.assertEqual(POLICY["combiner"], "OR")

    def test_one_explicit_promql_condition(self):
        self.assertEqual(len(POLICY["conditions"]), 1)
        condition = POLICY["conditions"][0]
        self.assertEqual(set(condition), {"display_name", "condition_prometheus_query_language"})
        self.assertEqual(condition["condition_prometheus_query_language"], [{
            "query": "${local.sample_service_availability_alert_query}",
            "duration": "120s", "evaluation_interval": "30s"}])

    def test_existing_gauges_and_bounded_scope(self):
        for name, metric in (("sample_service_available_replicas", "kube_deployment_status_replicas_available"),
                             ("sample_service_desired_replicas", "kube_deployment_spec_replicas")):
            query = LOCALS[name]
            self.assertIn(metric + "{", query)
            for matcher in ('project_id="${var.project_id}"', 'location="${var.gke_location}"',
                            'cluster="${var.gke_cluster_name}"', 'namespace=~"dev|stage|prod"',
                            'deployment="sample-service"'):
                self.assertIn(matcher, query)
            self.assertEqual(len(re.findall(r'\b(?:project_id|location|cluster|namespace|deployment)=', query)), 5)
        self.assertEqual(set(LOCALS), {"sample_service_available_replicas", "sample_service_desired_replicas",
                                      "sample_service_availability_alert_query"})

    def test_deduplication_and_environment_join(self):
        self.assertTrue(LOCALS["sample_service_available_replicas"].startswith("min by (" + GROUP + ")"))
        self.assertTrue(LOCALS["sample_service_desired_replicas"].startswith("max by (" + GROUP + ")"))
        query = LOCALS["sample_service_availability_alert_query"]
        self.assertEqual(query, "(${local.sample_service_available_replicas} < on (" + GROUP +
                         ") ${local.sample_service_desired_replicas})\nand on (" + GROUP +
                         ") (${local.sample_service_desired_replicas} > 0)")
        for forbidden in ("bool", "sum", "or vector", "uptime", "restart", "cpu", "memory"):
            self.assertNotIn(forbidden, " ".join(LOCALS.values()))

    def test_no_notifications_or_automatic_strategy(self):
        self.assertEqual(POLICY["notification_channels"], [])
        self.assertNotIn("alert_strategy", POLICY)
        self.assertEqual(set(POLICY), {"display_name", "project", "enabled", "combiner",
                                      "notification_channels", "documentation", "conditions", "depends_on"})
        guidance = POLICY["documentation"][0]["content"]
        for requirement in ("namespace/environment", "runtime release correlation", "dashboard review",
                            "continue, hold, or reject", "authorizes no"):
            self.assertIn(requirement, guidance)

    def test_public_identity_and_deferred_thresholds(self):
        text = json.dumps(CONFIG)
        self.assertNotRegex(text, r"(?i)(gserviceaccount|gs://|sha256:|[A-Z]:\\|projects/)")
        self.assertNotRegex(text, r"[\u0400-\u04ff]")
        for metric in ("sample_service_errors", "sample_service_latency_ms"):
            self.assertNotIn(metric, text)
        self.assertEqual(set(re.findall(r'\$\{var\.([^}]+)\}', text)),
                         {"project_id", "gke_cluster_name", "gke_location"})
        docs = (ROOT / "monitoring/alert-policies/README.md").read_text(encoding="utf-8")
        for limit in ("Error alerting is deferred", "Latency alerting is deferred", "missing vectors cannot prove health",
                      "one series per metric/environment", "30-second gauge samples"):
            self.assertIn(limit, docs)


if __name__ == "__main__":
    unittest.main()
