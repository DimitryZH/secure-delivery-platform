resource "google_monitoring_dashboard" "sample_service_health" {
  project = var.project_id
  dashboard_json = templatefile("${path.module}/../../monitoring/dashboards/sample-service-health.json.tftpl", {
    project_id = var.project_id
    cluster    = var.gke_cluster_name
    location   = var.gke_location
  })

  depends_on = [
    google_logging_metric.sample_service_requests,
    google_logging_metric.sample_service_errors,
    google_logging_metric.sample_service_latency,
  ]
}
