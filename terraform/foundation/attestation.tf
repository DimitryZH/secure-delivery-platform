# Authority is intentionally separate from image publishing. No trigger or
# actAs/tokenCreator grant to the build identity is created here.
resource "google_project_service" "attestation" {
  for_each = toset([
    "binaryauthorization.googleapis.com",
    "containeranalysis.googleapis.com",
    "cloudkms.googleapis.com",
  ])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_service_account" "attestation" {
  project      = var.project_id
  account_id   = "secure-delivery-attestation"
  display_name = "Secure delivery attestation authority"
  depends_on   = [google_project_service.required]
}

resource "google_kms_key_ring" "attestation" {
  project    = var.project_id
  name       = "secure-delivery-attestation"
  location   = var.region
  depends_on = [google_project_service.attestation]
}

resource "google_kms_crypto_key" "attestation" {
  name     = "verification"
  key_ring = google_kms_key_ring.attestation.id
  purpose  = "ASYMMETRIC_SIGN"
  version_template {
    algorithm        = "EC_SIGN_P256_SHA256"
    protection_level = "SOFTWARE"
  }
  lifecycle {
    prevent_destroy = true
  }
}

data "google_kms_crypto_key_version" "attestation" {
  crypto_key = google_kms_crypto_key.attestation.id
  version    = 1
}

resource "google_container_analysis_note" "verification" {
  project = var.project_id
  name    = "secure-delivery-verification"
  attestation_authority {
    hint {
      human_readable_name = "Secure delivery release metadata verification"
    }
  }
  depends_on = [google_project_service.attestation]
}

resource "google_binary_authorization_attestor" "verification" {
  project = var.project_id
  name    = "secure-delivery-verification"
  attestation_authority_note {
    note_reference = google_container_analysis_note.verification.id
    public_keys {
      id = data.google_kms_crypto_key_version.attestation.id
      pkix_public_key {
        public_key_pem      = data.google_kms_crypto_key_version.attestation.public_key[0].pem
        signature_algorithm = data.google_kms_crypto_key_version.attestation.public_key[0].algorithm
      }
    }
  }
}

resource "google_kms_crypto_key_iam_member" "attestation_signer" {
  crypto_key_id = google_kms_crypto_key.attestation.id
  role          = "roles/cloudkms.signerVerifier"
  member        = "serviceAccount:${google_service_account.attestation.email}"
}

resource "google_container_analysis_note_iam_member" "attestation_attacher" {
  project = var.project_id
  note    = google_container_analysis_note.verification.name
  role    = "roles/containeranalysis.notes.attacher"
  member  = "serviceAccount:${google_service_account.attestation.email}"
}

resource "google_binary_authorization_attestor_iam_member" "attestation_reader" {
  project  = var.project_id
  attestor = google_binary_authorization_attestor.verification.name
  role     = "roles/binaryauthorization.attestorsVerifier"
  member   = "serviceAccount:${google_service_account.attestation.email}"
}

resource "google_container_analysis_note_iam_member" "attestation_inspector" {
  project = var.project_id
  note    = google_container_analysis_note.verification.name
  role    = "roles/containeranalysis.notes.occurrences.viewer"
  member  = "serviceAccount:${google_service_account.attestation.email}"
}

# Creation and inspection only; no occurrence update/delete or note management.
resource "google_project_iam_custom_role" "attestation_occurrences" {
  project = var.project_id
  role_id = "attestationOccurrences"
  title   = "Create and inspect release attestations"
  permissions = [
    "containeranalysis.occurrences.create",
    "containeranalysis.occurrences.get",
    "containeranalysis.occurrences.list",
  ]
}

resource "google_project_iam_member" "attestation_occurrences" {
  project = var.project_id
  role    = google_project_iam_custom_role.attestation_occurrences.name
  member  = "serviceAccount:${google_service_account.attestation.email}"
}

resource "google_project_iam_member" "attestation_log_writer" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.attestation.email}"
}

# Dedicated staging avoids granting the signer read access to Terraform state
# or all project buckets. Upload rights remain with reviewed operator access.
resource "google_storage_bucket" "attestation_source" {
  project                     = var.project_id
  name                        = "${var.project_id}-attestation-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  lifecycle_rule {
    condition {
      age = 7
    }
    action {
      type = "Delete"
    }
  }
}

resource "google_storage_bucket_iam_member" "attestation_source_reader" {
  bucket = google_storage_bucket.attestation_source.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.attestation.email}"
}

output "attestation_service_account_email" {
  value = google_service_account.attestation.email
}

output "attestation_key_version" {
  value = data.google_kms_crypto_key_version.attestation.id
}

output "attestation_source_bucket" {
  value = google_storage_bucket.attestation_source.name
}

output "verification_attestor" {
  value = google_binary_authorization_attestor.verification.id
}
