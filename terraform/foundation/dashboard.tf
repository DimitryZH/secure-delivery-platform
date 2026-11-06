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

resource "google_monitoring_dashboard" "online_shop_dev" {
  project = var.project_id
  dashboard_json = templatefile("${path.module}/../../monitoring/dashboards/online-shop-dev/dashboard.json.tftpl", {
    queries = {
      for name in ["request-rate", "error-rate", "p95-latency", "observed-availability", "available-replicas", "desired-replicas"] :
      name => trimspace(templatefile("${path.module}/../../monitoring/dashboards/online-shop-dev/queries/${name}.promql.tftpl", {
        project_id = var.project_id
        cluster    = var.gke_cluster_name
        location   = var.gke_location
      }))
    }
  })
}
