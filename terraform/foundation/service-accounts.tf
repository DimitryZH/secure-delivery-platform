resource "google_service_account" "build" {
  project      = var.project_id
  account_id   = var.build_service_account_id
  display_name = "Secure delivery build identity"
  description  = "Build and verification identity for trusted release candidates."

  depends_on = [google_project_service.required]
}

resource "google_service_account" "deploy" {
  project      = var.project_id
  account_id   = var.deploy_service_account_id
  display_name = "Secure delivery deploy identity"
  description  = "Deployment identity for the controlled release path."

  depends_on = [google_project_service.required]
}

resource "google_service_account" "reviewer" {
  project      = var.project_id
  account_id   = var.reviewer_service_account_id
  display_name = "Secure delivery reviewer identity"
  description  = "Read-oriented identity for release review and troubleshooting."

  depends_on = [google_project_service.required]
}

resource "google_service_account" "node" {
  project      = var.project_id
  account_id   = var.node_service_account_id
  display_name = "Secure delivery node identity"
  description  = "Runtime node identity for the MVP GKE cluster."

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "build_artifact_registry_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.build.email}"
}

resource "google_project_iam_member" "build_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.build.email}"
}

resource "google_project_iam_member" "deploy_gke_developer" {
  project = var.project_id
  role    = "roles/container.developer"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "deploy_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_project_iam_member" "reviewer_log_viewer" {
  project = var.project_id
  role    = "roles/logging.viewer"
  member  = "serviceAccount:${google_service_account.reviewer.email}"
}

resource "google_project_iam_member" "reviewer_monitoring_viewer" {
  project = var.project_id
  role    = "roles/monitoring.viewer"
  member  = "serviceAccount:${google_service_account.reviewer.email}"
}

resource "google_project_iam_member" "node_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.node.email}"
}

resource "google_project_iam_member" "node_monitoring_metric_writer" {
  project = var.project_id
  role    = "roles/monitoring.metricWriter"
  member  = "serviceAccount:${google_service_account.node.email}"
}
