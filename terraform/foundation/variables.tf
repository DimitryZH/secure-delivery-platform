variable "project_id" {
  description = "Google Cloud project ID for the secure delivery platform baseline."
  type        = string

  validation {
    condition = (
      var.project_id != "replace-with-your-project-id" &&
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    )
    error_message = "project_id must be a valid Google Cloud project ID and must not use the example placeholder."
  }
}

variable "region" {
  description = "Google Cloud region for regional baseline resources."
  type        = string
  default     = "us-central1"
}

variable "enabled_services" {
  description = "Google Cloud APIs required for the MVP trusted release baseline."
  type        = set(string)
  default = [
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
  ]
}

variable "artifact_registry_repository_id" {
  description = "Artifact Registry Docker repository ID for release candidate images."
  type        = string
  default     = "secure-delivery"
}

variable "artifact_registry_description" {
  description = "Description for the Artifact Registry repository used by the trusted release path."
  type        = string
  default     = "Container images for the secure delivery platform trusted release path."
}

variable "build_service_account_id" {
  description = "Service account ID for the build and verification identity."
  type        = string
  default     = "secure-delivery-build"
}

variable "deploy_service_account_id" {
  description = "Service account ID for the deployment identity."
  type        = string
  default     = "secure-delivery-deploy"
}

variable "reviewer_service_account_id" {
  description = "Service account ID for the release reviewer identity."
  type        = string
  default     = "secure-delivery-reviewer"
}

variable "node_service_account_id" {
  description = "Service account ID for the GKE node identity."
  type        = string
  default     = "secure-delivery-node"
}

variable "gke_cluster_name" {
  description = "Name of the single GKE cluster used by the MVP baseline."
  type        = string
  default     = "secure-delivery-platform"
}

variable "gke_location" {
  description = "Google Cloud zone or region for the MVP GKE cluster."
  type        = string
  default     = "us-central1-a"
}

variable "gke_initial_node_count" {
  description = "Initial node count for the MVP GKE cluster."
  type        = number
  default     = 1
}

variable "gke_node_machine_type" {
  description = "Machine type for the MVP GKE cluster node pool."
  type        = string
  default     = "e2-standard-2"
}

variable "environment_namespaces" {
  description = "Kubernetes namespaces used to model MVP environment progression."
  type        = set(string)
  default     = ["dev", "stage", "prod"]
}
