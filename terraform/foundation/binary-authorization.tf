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
    cluster          = "${var.gke_location}.${var.gke_cluster_name}"
    evaluation_mode  = "REQUIRE_ATTESTATION"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
    # Keep this name known during planning: legacy nested-set handling can
    # collapse an unknown computed attestor ID to an empty set.
    require_attestations_by = ["projects/${var.project_id}/attestors/${google_binary_authorization_attestor.verification.name}"]
  }
  # The API requires the attestor to exist before referencing it in policy.
  depends_on = [google_binary_authorization_attestor.verification]
}
