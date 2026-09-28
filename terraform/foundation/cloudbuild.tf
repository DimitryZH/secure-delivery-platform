resource "google_cloudbuild_trigger" "sample_service_image" {
  project     = var.project_id
  location    = var.region
  name        = "sample-service-image-build"
  description = "Build and publish the sample-service image from the main branch."

  filename        = "cloudbuild/cloudbuild-ci.yaml"
  service_account = google_service_account.build.id

  included_files = [
    "app/sample-service/**",
    "cloudbuild/cloudbuild-ci.yaml",
  ]

  repository_event_config {
    repository = "projects/${var.project_id}/locations/${var.region}/connections/secure-delivery-github/repositories/secure-delivery-platform"

    push {
      branch = "^main$"
    }
  }

  substitutions = {
    _LOCATION   = var.region
    _REPOSITORY = google_artifact_registry_repository.release_images.repository_id
  }

  depends_on = [google_project_iam_member.build_cloud_build_builder]
}
