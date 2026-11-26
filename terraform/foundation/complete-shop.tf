# #100 proposal only. Apply requires review of the full saved plan and separate
# authorization. Preserve both shared node pools and the selected capacity mode.
resource "google_container_node_pool" "complete_shop" {
  project    = var.project_id
  location   = var.gke_location
  cluster    = google_container_cluster.platform.name
  name       = "shop-dev-capacity"
  node_count = local.gke_managed_pool_node_count

  upgrade_settings {
    max_surge       = 1
    max_unavailable = 0
  }

  node_config {
    machine_type    = "e2-standard-4"
    disk_size_gb    = 50
    disk_type       = "pd-standard"
    service_account = google_service_account.node.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
    workload_metadata_config {
      mode = "GKE_METADATA"
    }
    labels = {
      "delivery-capacity" = "complete-shop-dev"
    }
  }

  management {
    auto_repair  = true
    auto_upgrade = true
  }

  lifecycle {
    prevent_destroy = true
  }
}

# The original catalog-only exclusion remains unchanged. These nine services
# plus native Redis stdout are owned by the same independently configured agent.
resource "google_logging_project_exclusion" "complete_shop_stdout" {
  project     = var.project_id
  name        = "complete-shop-stdout-owned-by-collector"
  description = "Avoid duplicate managed-agent ingestion for complete-shop dev stdout."
  filter      = <<-FILTER
    resource.type="k8s_container"
    resource.labels.cluster_name="${var.gke_cluster_name}"
    resource.labels.namespace_name="dev"
    resource.labels.container_name=("server" OR "redis")
    labels."k8s-pod/app"=("adservice" OR "cartservice" OR "checkoutservice" OR "currencyservice" OR "emailservice" OR "frontend" OR "paymentservice" OR "recommendationservice" OR "shippingservice" OR "redis-cart")
    log_id("stdout")
  FILTER
}
