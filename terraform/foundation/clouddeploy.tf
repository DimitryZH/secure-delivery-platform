# Cloud Deploy orchestrates progression; Binary Authorization remains admission.
# Namespace selection is in the matching Skaffold profile's rendered manifests:
# Cloud Deploy GKE targets have no namespace field.
locals {
  promotion_environments = ["dev", "stage", "prod"]
}

resource "google_project_service" "clouddeploy" {
  project            = var.project_id
  service            = "clouddeploy.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_iam_member" "deploy_clouddeploy_job_runner" {
  project = var.project_id
  role    = "roles/clouddeploy.jobRunner"
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_clouddeploy_target" "environment" {
  for_each         = toset(local.promotion_environments)
  project          = var.project_id
  location         = var.region
  name             = each.value
  description      = "Sample service in the ${each.value} namespace; selected by the matching Skaffold profile."
  require_approval = each.value != "dev"

  gke {
    cluster = google_container_cluster.platform.id
  }

  execution_configs {
    usages          = ["RENDER", "DEPLOY"]
    service_account = google_service_account.deploy.email
  }

  depends_on = [
    google_project_service.clouddeploy,
    google_project_iam_member.deploy_clouddeploy_job_runner,
    google_project_iam_member.deploy_gke_developer,
    kubernetes_namespace.environment,
  ]
}

resource "google_clouddeploy_delivery_pipeline" "sample_service" {
  project     = var.project_id
  location    = var.region
  name        = "sample-service"
  description = "Promote one verified, attested digest through dev, stage, and prod."

  serial_pipeline {
    dynamic "stages" {
      for_each = local.promotion_environments
      content {
        target_id = google_clouddeploy_target.environment[stages.value].name
        profiles  = [stages.value]
      }
    }
  }
}
