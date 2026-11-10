terraform {
  required_version = ">= 1.6.0"
  backend "gcs" {}
  required_providers {
    google     = { source = "hashicorp/google", version = "~> 5.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.0" }
  }
}
variable "project_id" { type = string }
variable "cloud_connection" {
  description = "Exact kubernetes_connection output of the applied cloud foundation; not a guessed endpoint."
  sensitive   = true
  type        = object({ project_id = string, endpoint = string, cluster_ca_certificate = string, environment_namespaces = list(string) })
}
provider "google" {
  project               = var.project_id
  user_project_override = true
  billing_project       = var.project_id
}
data "google_client_config" "current" {}
provider "kubernetes" {
  host                   = "https://${var.cloud_connection.endpoint}"
  token                  = data.google_client_config.current.access_token
  cluster_ca_certificate = base64decode(var.cloud_connection.cluster_ca_certificate)
}
resource "kubernetes_namespace" "environment" {
  for_each = toset(nonsensitive(var.cloud_connection.environment_namespaces))
  lifecycle {
    precondition {
      condition     = var.cloud_connection.project_id == var.project_id
      error_message = "Connection output must belong to the selected cloud foundation project."
    }
  }
  metadata {
    name = each.value
    labels = {
      "app.kubernetes.io/part-of"     = "secure-delivery-platform"
      "delivery.platform/environment" = each.value
    }
  }
}
