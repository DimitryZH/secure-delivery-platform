# Initial greenfield cloud root deliberately excludes endpoint/synthetic resources.
variable "shop_edge_enforce_evaluated_rules" {
  type    = bool
  default = false
  validation {
    condition     = !var.shop_edge_enforce_evaluated_rules
    error_message = "Endpoint is deferred in this greenfield root."
  }
}
variable "shop_observability_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.shop_observability_enabled
    error_message = "Synthetic provisioning is deferred in this greenfield root."
  }
}
variable "shop_observability_schedule_enabled" {
  type    = bool
  default = false
  validation {
    condition     = !var.shop_observability_schedule_enabled
    error_message = "Synthetic scheduling is deferred in this greenfield root."
  }
}

output "greenfield_pool_creation" {
  description = "Fail closed if historical pool adoption mode is supplied to this root."
  value       = var.gke_create_separate_default_pool
  precondition {
    condition     = var.gke_create_separate_default_pool
    error_message = "Greenfield requires a separately created default-pool after removal of the temporary initial pool."
  }
}
