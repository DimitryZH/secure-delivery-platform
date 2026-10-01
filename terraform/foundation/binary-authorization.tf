# Adopt the existing project singleton at apply time; planning does not import
# it into remote state or change the live policy.
import {
  to = google_binary_authorization_policy.application
  id = "projects/${var.project_id}"
}

resource "google_binary_authorization_policy" "application" {
  project                       = var.project_id
  description                   = "Require verified release attestations on the platform cluster."
  global_policy_evaluation_mode = "ENABLE"

  # Preserve the existing behavior outside the explicitly protected cluster.
  default_admission_rule {
    evaluation_mode  = "ALWAYS_ALLOW"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
  }

  # Applies to every namespace, including dev, stage, and prod. System images
  # are handled by Google's maintained global policy, not namespace bypasses.
  cluster_admission_rules {
    cluster                 = "${var.gke_location}.${var.gke_cluster_name}"
    evaluation_mode         = "REQUIRE_ATTESTATION"
    enforcement_mode        = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    require_attestations_by = [google_binary_authorization_attestor.verification.id]
  }
}
