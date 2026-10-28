# Independent catalog verification reads the producing build by its exact ID.
# Cloud Build IAM is project-scoped; do not grant list, create, update or cancel.
resource "google_project_iam_custom_role" "catalog_build_evidence_reader" {
  project     = var.project_id
  role_id     = "catalogBuildEvidenceReader"
  title       = "Read catalog build evidence"
  description = "Read producing Cloud Build executions for independent catalog release verification."
  permissions = [
    "cloudbuild.builds.get",
    "serviceusage.services.use",
  ]
}

resource "google_project_iam_member" "attestation_build_evidence_reader" {
  project = var.project_id
  role    = google_project_iam_custom_role.catalog_build_evidence_reader.name
  member  = "serviceAccount:${google_service_account.attestation.email}"
}

# Registry manifest/config readback uses the existing release repository only.
# Keep image publication with the builder and signing with the attestation account.
resource "google_artifact_registry_repository_iam_member" "attestation_image_reader" {
  project    = google_artifact_registry_repository.release_images.project
  location   = google_artifact_registry_repository.release_images.location
  repository = google_artifact_registry_repository.release_images.repository_id
  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:${google_service_account.attestation.email}"
}
