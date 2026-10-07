"""Offline contract checks for bounded release-health metric definitions."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
CONFIG = json.loads((ROOT / "terraform/foundation/logging-metrics.tf.json").read_text(encoding="utf-8"))
METRICS = CONFIG["resource"]["google_logging_metric"]
COMMON = CONFIG["locals"]["sample_service_request_filter"]


class ReleaseHealthMetricsTest(unittest.TestCase):
    def test_only_three_metrics_reuse_foundation(self):
        self.assertEqual(set(CONFIG), {"locals", "resource"})
        self.assertEqual(set(CONFIG["resource"]), {"google_logging_metric"})
        self.assertEqual(set(METRICS), {"sample_service_requests", "sample_service_errors", "sample_service_latency"})
        for metric in METRICS.values():
            self.assertEqual(metric["project"], "${var.project_id}")
            self.assertEqual(metric["depends_on"], ["google_project_service.required"])
            self.assertTrue(metric["filter"].startswith("${local.sample_service_request_filter}"))

    def test_common_filter_excludes_unrelated_or_ambiguous_events(self):
        for constraint in ('resource.type="k8s_container"',
                           'resource.labels.cluster_name="${var.gke_cluster_name}"',
                           'resource.labels.container_name="sample-service"', 'log_id("stdout")',
                           'jsonPayload.event="http_request"', 'jsonPayload.service="sample-service"',
                           '(jsonPayload.health_check=true OR jsonPayload.health_check=false)',
                           'jsonPayload.status >= 100', 'jsonPayload.status < 600'):
            self.assertIn(constraint, COMMON)
        pairs = re.findall(r'resource.labels.namespace_name="([^"]+)" AND jsonPayload.environment="([^"]+)"', COMMON)
        self.assertEqual(pairs, [(env, env) for env in ("dev", "stage", "prod")])
        self.assertEqual(COMMON.count(" OR "), 3)
        for field in ("path", "pod_name", "severity", "release", "digest"):
            self.assertNotIn(field, COMMON)

    def test_labels_are_bounded_and_have_matching_extractors(self):
        for metric in METRICS.values():
            labels = {label["key"]: label["value_type"] for label in metric["metric_descriptor"][0]["labels"]}
            self.assertEqual(labels, {"environment": "STRING", "health_check": "BOOL"})
            self.assertEqual(metric["label_extractors"], {
                "environment": "EXTRACT(jsonPayload.environment)",
                "health_check": "EXTRACT(jsonPayload.health_check)"})
        text = json.dumps(CONFIG)
        self.assertNotRegex(text, r"(?i)(pod_name|commit.sha|build.id|release.id|image.digest|trust.signal|service.account)")
        self.assertNotRegex(text, r"(?i)(iam\.gserviceaccount\.com|gs://|projects/|[A-Z]:\\)")

    def test_response_counters_and_error_population(self):
        for key in ("sample_service_requests", "sample_service_errors"):
            metric = METRICS[key]
            descriptor = metric["metric_descriptor"][0]
            self.assertEqual((descriptor["metric_kind"], descriptor["value_type"], descriptor["unit"]),
                             ("DELTA", "INT64", "1"))
            self.assertNotIn("value_extractor", metric)
            self.assertNotIn("bucket_options", metric)
        self.assertEqual(METRICS["sample_service_requests"]["filter"], "${local.sample_service_request_filter}")
        self.assertEqual(METRICS["sample_service_errors"]["filter"],
                         "${local.sample_service_request_filter}\njsonPayload.status >= 400")

    def test_latency_is_numeric_distribution_with_finite_ordered_buckets(self):
        metric = METRICS["sample_service_latency"]
        descriptor = metric["metric_descriptor"][0]
        self.assertEqual((descriptor["metric_kind"], descriptor["value_type"], descriptor["unit"]),
                         ("DELTA", "DISTRIBUTION", "ms"))
        self.assertEqual(metric["value_extractor"], "EXTRACT(jsonPayload.latency_ms)")
        self.assertEqual(metric["filter"], "${local.sample_service_request_filter}\njsonPayload.latency_ms >= 0")
        bounds = metric["bucket_options"][0]["explicit_buckets"][0]["bounds"]
        self.assertEqual(bounds, [1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000])
        self.assertTrue(all(a < b for a, b in zip([0] + bounds, bounds)))

    def test_availability_reuses_collected_deployment_state(self):
        documentation = (ROOT / "docs/operator-runbook.md").read_text(encoding="utf-8")
        for metric in ("kube_deployment_status_replicas_available/gauge", "kube_deployment_spec_replicas/gauge"):
            self.assertIn("prometheus.googleapis.com/" + metric, documentation)
        self.assertIn("Missing/stale series and scale-to-zero are not success", documentation)
        self.assertIn("nextPageToken", documentation)
        self.assertIn("aggregation does not reduce ingestion cardinality", (ROOT / "monitoring/log-based-metrics/README.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
