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

  node_config {
    machine_type    = var.gke_node_machine_type
    service_account = google_service_account.node.email
    oauth_scopes = [
      "https://www.googleapis.com/auth/cloud-platform",
    ]
  }

  depends_on = [google_project_service.required]
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
