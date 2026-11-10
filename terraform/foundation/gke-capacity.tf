variable "gke_capacity_mode" {
  description = "Explicit managed-pool capacity: running (one node per pool) or paused (zero). Null preserves historical adoption only; separate-pool roots require an explicit mode in private inputs."
  type        = string
  default     = null

  validation {
    condition     = var.gke_capacity_mode == null ? true : contains(["running", "paused"], var.gke_capacity_mode)
    error_message = "gke_capacity_mode must be running or paused."
  }
}

locals {
  gke_managed_pool_node_count = var.gke_capacity_mode == "paused" ? 0 : 1
}
