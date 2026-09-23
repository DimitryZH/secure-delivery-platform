variable "project_id" {
  description = "Google Cloud project ID that will own the Terraform state bucket."
  type        = string

  validation {
    condition = (
      var.project_id != "replace-with-your-project-id" &&
      can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.project_id))
    )
    error_message = "project_id must be a valid Google Cloud project ID and must not use the example placeholder."
  }
}

variable "state_bucket_name" {
  description = "Globally unique name for the Google Cloud Storage bucket that will hold Terraform state."
  type        = string

  validation {
    condition = (
      var.state_bucket_name != "replace-with-globally-unique-state-bucket-name" &&
      can(regex("^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$", var.state_bucket_name)) &&
      !strcontains(var.state_bucket_name, "..")
    )
    error_message = "state_bucket_name must be 3 to 63 valid characters, start and end with a letter or number, and must not use the example placeholder."
  }
}

variable "location" {
  description = "Google Cloud Storage location for the state bucket. The US multi-region is the safe default; override it to meet residency or cost requirements."
  type        = string
  default     = "US"

  validation {
    condition     = length(trimspace(var.location)) > 0
    error_message = "location must not be empty."
  }
}
