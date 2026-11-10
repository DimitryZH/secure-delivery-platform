data "google_client_config" "current" {}

provider "kubernetes" {
  host                   = "https://${google_container_cluster.platform.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(google_container_cluster.platform.master_auth[0].cluster_ca_certificate)
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
