# Proposed for #93. Applying this configuration is a separate reviewed operation.
resource "google_service_account" "catalog_telemetry" {
  project      = var.project_id
  account_id   = "catalog-telemetry"
  display_name = "Catalog Collector export identity"
}

resource "google_project_iam_member" "catalog_telemetry_export" {
  for_each = toset([
    "roles/cloudtrace.agent",
    "roles/monitoring.metricWriter",
    "roles/logging.logWriter",
  ])
  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.catalog_telemetry.email}"
}

resource "google_service_account_iam_member" "catalog_collector_identity" {
  service_account_id = google_service_account.catalog_telemetry.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[dev/catalog-collector]"
}

# Already enabled in the inspected project; declare lifecycle without disabling it.
resource "google_project_service" "catalog_trace" {
  project            = var.project_id
  service            = "cloudtrace.googleapis.com"
  disable_on_destroy = false
}

# Only the managed agent's original catalog stdout copy is excluded. The
# Collector's online-shop/catalog stream remains ingested. Sample logs stay intact.
resource "google_logging_project_exclusion" "catalog_stdout" {
  project     = var.project_id
  name        = "catalog-stdout-owned-by-collector"
  description = "Collector maps catalog JSON trace IDs to native LogEntry linkage."
  filter      = <<-FILTER
    resource.type="k8s_container"
    resource.labels.cluster_name="${var.gke_cluster_name}"
    resource.labels.namespace_name="dev"
    resource.labels.container_name="catalog"
    labels."k8s-pod/app"="productcatalogservice"
    log_id("stdout")
  FILTER
}

resource "google_clouddeploy_delivery_pipeline" "catalog_dev" {
  project     = var.project_id
  location    = var.region
  name        = "catalog-dev"
  description = "Reviewed catalog-v1 and independently trusted Collector, dev only."
  serial_pipeline {
    stages {
      target_id = google_clouddeploy_target.environment["dev"].name
      profiles  = ["dev"]
    }
  }
}
