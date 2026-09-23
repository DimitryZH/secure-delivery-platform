output "state_bucket_name" {
  description = "Name of the Google Cloud Storage bucket for Terraform state."
  value       = google_storage_bucket.terraform_state.name
}

output "foundation_backend_prefix" {
  description = "Object prefix reserved for the foundation Terraform state."
  value       = "secure-delivery-platform/foundation"
}
