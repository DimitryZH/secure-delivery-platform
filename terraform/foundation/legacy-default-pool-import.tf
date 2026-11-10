# Declarative adoption is plan-only until a separately authorized apply. It
# preserves the existing one-node pool rather than creating/replacing a cluster.
import {
  to = google_container_node_pool.existing_default
  id = "${var.project_id}/${var.gke_location}/${var.gke_cluster_name}/default-pool"
}
