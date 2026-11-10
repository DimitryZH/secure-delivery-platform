resource "google_container_cluster" "platform" {
  project  = var.project_id
  name     = var.gke_cluster_name
  location = var.gke_location

  remove_default_node_pool = var.gke_create_separate_default_pool
  initial_node_count       = var.gke_initial_node_count
  deletion_protection      = false

  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
  }

  # Gateway controller owns ALB resources; no Terraform ownership overlap.
  gateway_api_config {
    channel = "CHANNEL_STANDARD"
  }

  # Dedicated Collector identity; application Pods receive no exporter grants.
  workload_identity_config {
    workload_pool = "${var.project_id}.svc.id.goog"
  }

  node_config {
    machine_type    = var.gke_node_machine_type
    service_account = google_service_account.node.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition = !var.gke_create_separate_default_pool || (
        var.gke_initial_node_count == 1 &&
        var.gke_node_machine_type == "e2-standard-2" &&
        can(regex("^[a-z]+-[a-z]+[0-9]-[a-z]$", var.gke_location))
      )
      error_message = "Reviewed greenfield sizing requires one temporary e2-standard-2 node in a single zone."
    }
    # The existing default pool is adopted below. Its mutable settings must
    # not be updated through the cluster's create-time node_config (ForceNew).
    ignore_changes = [node_config]
  }

  # Install the attestor requirement before enabling admission enforcement.
  depends_on = [google_project_service.required, google_binary_authorization_policy.application]
}

resource "google_container_node_pool" "existing_default" {
  project    = var.project_id
  location   = var.gke_location
  cluster    = google_container_cluster.platform.name
  name       = "default-pool"
  node_count = var.gke_create_separate_default_pool ? local.gke_managed_pool_node_count : null

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = var.gke_node_machine_type
    service_account = google_service_account.node.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
  }

  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.gke_create_separate_default_pool ? var.gke_capacity_mode != null : var.gke_capacity_mode != "paused"
      error_message = "Separate-pool roots require explicit gke_capacity_mode in private inputs; paused is unsupported for historical default-pool adoption."
    }
  }

  depends_on = [google_container_cluster.platform]
}
