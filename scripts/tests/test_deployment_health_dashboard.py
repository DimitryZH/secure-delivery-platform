"""Offline checks for the release-focused dashboard query contract."""
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = (ROOT / "monitoring/dashboards/sample-service-health.json.tftpl").read_text(encoding="utf-8")
DASHBOARD = json.loads(TEMPLATE)
WIDGETS = DASHBOARD["gridLayout"]["widgets"]
QUERIES = [dataset["timeSeriesQuery"]["timeSeriesFilter"]
           for widget in WIDGETS for dataset in widget["xyChart"]["dataSets"]]


class DeploymentHealthDashboardTest(unittest.TestCase):
    def test_single_resource_and_compact_signal_set(self):
        config = (ROOT / "terraform/foundation/dashboard.tf").read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'resource "([^"]+)" "([^"]+)"', config),
                         [("google_monitoring_dashboard", "sample_service_health")])
        self.assertIn('project = var.project_id', config)
        self.assertIn('templatefile(', config)
        self.assertEqual(len(WIDGETS), 5)
        types = {re.search(r'metric.type="([^"]+)"', query["filter"])[1] for query in QUERIES}
        self.assertEqual(types, {
            "prometheus.googleapis.com/kube_deployment_status_replicas_available/gauge",
            "prometheus.googleapis.com/kube_deployment_spec_replicas/gauge",
            "logging.googleapis.com/user/sample_service_requests",
            "logging.googleapis.com/user/sample_service_errors",
            "logging.googleapis.com/user/sample_service_latency_ms"})

    def test_only_bounded_environment_selector(self):
        self.assertEqual(DASHBOARD["dashboardFilters"], [{
            "filterType": "VALUE_ONLY", "templateVariable": "environment",
            "valueType": "STRING", "stringValue": "dev",
            "stringArray": {"values": ["dev", "stage", "prod"]}}])
        for query in QUERIES:
            self.assertIn('one_of("dev", "stage", "prod")', query["filter"])
            self.assertIn('monitoring.regex.full_match($${environment})', query["filter"])
        self.assertEqual(set(re.findall(r'\$\$\{([^}]+)\}', TEMPLATE)), {"environment"})

    def test_all_queries_scope_configured_workload(self):
        for query in QUERIES:
            f = query["filter"]
            for value in ('${project_id}', '${location}', '${cluster}'):
                self.assertIn(value, f)
            if 'resource.type="prometheus_target"' in f:
                self.assertIn('metric.labels.deployment="sample-service"', f)
                self.assertIn('resource.labels.namespace=', f)
            else:
                self.assertIn('resource.type="k8s_container"', f)
                self.assertIn('resource.labels.container_name="sample-service"', f)
                self.assertIn('resource.labels.namespace_name=', f)
                self.assertIn('metric.labels.environment=', f)

    def test_health_populations_and_delta_counts(self):
        self.assertIn('metric.labels.health_check="false"', QUERIES[2]["filter"])
        self.assertIn('sample_service_errors', QUERIES[3]["filter"])
        self.assertNotIn('health_check=', QUERIES[3]["filter"])
        self.assertIn('metric.labels.health_check="true"', QUERIES[5]["filter"])
        for index in (2, 3, 5):
            self.assertEqual(QUERIES[index]["aggregation"], {
                "alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_SUM",
                "crossSeriesReducer": "REDUCE_SUM",
                "groupByFields": ["resource.labels.namespace_name", "metric.labels.environment"]})
            self.assertNotIn("secondaryAggregation", QUERIES[index])

    def test_latency_merges_before_percentile(self):
        query = QUERIES[4]
        self.assertIn('sample_service_latency_ms', query["filter"])
        self.assertIn('metric.labels.health_check="false"', query["filter"])
        self.assertEqual(query["aggregation"]["perSeriesAligner"], "ALIGN_SUM")
        self.assertEqual(query["aggregation"]["crossSeriesReducer"], "REDUCE_SUM")
        self.assertEqual(query["secondaryAggregation"], {
            "alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_PERCENTILE_95"})
        self.assertNotIn('ALIGN_MEAN', TEMPLATE)

    def test_availability_never_sums_collectors(self):
        for query, operation in zip(QUERIES[:2], ("MIN", "MAX")):
            self.assertEqual(query["aggregation"], {
                "alignmentPeriod": "60s", "perSeriesAligner": "ALIGN_" + operation,
                "crossSeriesReducer": "REDUCE_" + operation,
                "groupByFields": ["resource.labels.namespace"]})
        self.assertNotIn('pod_name', TEMPLATE)
        self.assertNotIn('ALIGN_RATE', TEMPLATE)

    def test_template_tokens_and_public_boundary(self):
        self.assertEqual(set(re.findall(r'(?<!\$)\$\{([^}]+)\}', TEMPLATE)),
                         {"project_id", "cluster", "location"})
        self.assertNotRegex(TEMPLATE, r"(?i)(gserviceaccount|gs://|sha256:|[A-Z]:\\|projects/)")
        self.assertNotRegex(TEMPLATE, r"[\u0400-\u04ff]")
        self.assertNotIn('alertPolicy', TEMPLATE)
        self.assertNotIn('thresholds', TEMPLATE)
        for env in ("dev", "stage", "prod"):
            rendered = TEMPLATE.replace('$${environment}', '${environment}')
            for key in ("project_id", "cluster", "location"):
                rendered = rendered.replace('${' + key + '}', 'test-' + key)
            value = json.loads(rendered)
            for widget in value["gridLayout"]["widgets"]:
                for dataset in widget["xyChart"]["dataSets"]:
                    f = dataset["timeSeriesQuery"]["timeSeriesFilter"]["filter"]
                    f = f.replace('${environment}', json.dumps(env))
                    self.assertNotIn('${', f)
                    self.assertIn('monitoring.regex.full_match("' + env + '")', f)


if __name__ == "__main__":
    unittest.main()
