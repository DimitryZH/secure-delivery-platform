data "google_client_config" "current" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.platform.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.platform.master_auth[0].cluster_ca_certificate)
}

resource "google_container_cluster" "platform" {
  project  = var.project_id
  name     = var.gke_cluster_name
  location = var.gke_location

  initial_node_count  = var.gke_initial_node_count
  deletion_protection = false

  binary_authorization {
    evaluation_mode = "PROJECT_SINGLETON_POLICY_ENFORCE"
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
    # The existing default pool is adopted below. Its mutable settings must
    # not be updated through the cluster's create-time node_config (ForceNew).
    ignore_changes = [node_config]
  }

  # Install the attestor requirement before enabling admission enforcement.
  depends_on = [google_project_service.required, google_binary_authorization_policy.application]
}

# Declarative adoption is plan-only until a separately authorized apply. It
# preserves the existing one-node pool rather than creating/replacing a cluster.
import {
  to = google_container_node_pool.existing_default
  id = "${var.project_id}/${var.gke_location}/${var.gke_cluster_name}/default-pool"
}

resource "google_container_node_pool" "existing_default" {
  project  = var.project_id
  location = var.gke_location
  cluster  = google_container_cluster.platform.name
  name     = "default-pool"

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
  }

  depends_on = [google_container_cluster.platform]
}

resource "kubernetes_namespace" "environment" {
  for_each = var.environment_namespaces

  metadata {
    name = each.value
    labels = {
      "app.kubernetes.io/part-of"     = "secure-delivery-platform"
      "delivery.platform/environment" = each.value
    }
  }

  depends_on = [google_container_cluster.platform]
}
