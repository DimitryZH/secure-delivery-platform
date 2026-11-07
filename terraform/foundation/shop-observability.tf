# Reviewed #115 proposal. Provisioning and scheduling require separate plans.
provider "google-beta" {
  project               = var.project_id
  region                = var.region
  user_project_override = true
  billing_project       = var.project_id
}

variable "shop_observability_enabled" {
  type        = bool
  default     = false
  description = "Provision the reviewed synthetic function, operator channel and application alert."
}

variable "shop_observability_schedule_enabled" {
  type        = bool
  default     = false
  description = "Create scheduled checks and enable alerts only after function/channel readback."
}

variable "shop_operator_email" {
  type        = string
  default     = null
  sensitive   = true
  description = "Operator email supplied privately before the reviewed plan."

  validation {
    condition     = var.shop_operator_email == null ? true : can(regex("^[^[:space:]@]+@[^[:space:]@]+[.][^[:space:]@]+$", var.shop_operator_email))
    error_message = "Supply a specific operator email through private inputs."
  }
}

variable "shop_synthetic_source_zip" {
  type        = string
  default     = null
  description = "Absolute path to the deterministic ZIP built by monitoring/online-shop/synthetic/package-source.py."
}

locals {
  shop_monitor_schedule = var.shop_observability_enabled && var.shop_observability_schedule_enabled
  shop_synthetic_sha    = var.shop_synthetic_source_zip == null ? "unpackaged" : filesha256(var.shop_synthetic_source_zip)
  shop_monitor_labels   = { application = "online-shop", environment = "dev", issue = "115" }
}

data "google_project" "shop_monitoring" {
  count      = var.shop_observability_enabled ? 1 : 0
  project_id = var.project_id
}

resource "google_project_service" "shop_monitoring" {
  for_each           = var.shop_observability_enabled ? toset(["cloudfunctions.googleapis.com", "run.googleapis.com", "pubsub.googleapis.com"]) : toset([])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service_identity" "shop_monitoring" {
  provider = google-beta
  count    = var.shop_observability_enabled ? 1 : 0
  project  = var.project_id
  service  = "monitoring.googleapis.com"

  depends_on = [google_project_service.required]
}

resource "google_monitoring_notification_channel" "shop_operator" {
  count        = var.shop_observability_enabled ? 1 : 0
  project      = var.project_id
  display_name = "Online Shop dev operator"
  type         = "email"
  labels       = var.shop_operator_email == null ? {} : { email_address = var.shop_operator_email }
  user_labels  = local.shop_monitor_labels

  lifecycle {
    precondition {
      condition     = var.shop_operator_email != null
      error_message = "Operator email is required before provisioning."
    }
  }
}

resource "google_service_account" "shop_synthetic" {
  for_each     = var.shop_observability_enabled ? toset(["runtime", "build"]) : toset([])
  project      = var.project_id
  account_id   = "shop-synthetic-${each.key}"
  display_name = "Online Shop synthetic ${each.key}"
}

resource "google_project_iam_member" "shop_synthetic_trace" {
  count   = var.shop_observability_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/cloudtrace.agent"
  member  = "serviceAccount:${google_service_account.shop_synthetic["runtime"].email}"
}

resource "google_project_iam_member" "shop_synthetic_build_logs" {
  count   = var.shop_observability_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.shop_synthetic["build"].email}"
}

resource "google_project_iam_member" "shop_synthetic_build_service_usage" {
  count   = var.shop_observability_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/serviceusage.serviceUsageConsumer"
  member  = "serviceAccount:${google_service_account.shop_synthetic["build"].email}"
}

resource "google_storage_bucket" "shop_synthetic_source" {
  count                       = var.shop_observability_enabled ? 1 : 0
  project                     = var.project_id
  name                        = "${var.project_id}-shop-synthetic-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
}

resource "google_storage_bucket_object" "shop_synthetic_source" {
  count        = var.shop_observability_enabled ? 1 : 0
  bucket       = google_storage_bucket.shop_synthetic_source[0].name
  name         = "browse-v1/${local.shop_synthetic_sha}.zip"
  source       = var.shop_synthetic_source_zip
  content_type = "application/zip"

  lifecycle {
    precondition {
      condition     = var.shop_synthetic_source_zip != null
      error_message = "Package the reviewed synthetic source before planning."
    }
  }
}

resource "google_storage_bucket_iam_member" "shop_synthetic_source_reader" {
  count  = var.shop_observability_enabled ? 1 : 0
  bucket = google_storage_bucket.shop_synthetic_source[0].name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.shop_synthetic["build"].email}"
}

# Functions copies reviewed source into its regional managed source bucket.
resource "google_project_iam_member" "shop_synthetic_managed_source_reader" {
  count   = var.shop_observability_enabled ? 1 : 0
  project = var.project_id
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.shop_synthetic["build"].email}"

  condition {
    title       = "only-shop-synthetic-managed-source"
    description = "Only this function's managed source objects."
    expression  = "resource.type == 'storage.googleapis.com/Object' && resource.name.startsWith('projects/_/buckets/gcf-v2-sources-${data.google_project.shop_monitoring[0].number}-${var.region}/objects/shop-dev-browse/')"
  }
}

resource "google_artifact_registry_repository" "shop_synthetic" {
  count         = var.shop_observability_enabled ? 1 : 0
  project       = var.project_id
  location      = var.region
  repository_id = "shop-monitoring-functions"
  format        = "DOCKER"
  description   = "Synthetic function build images."
}

resource "google_artifact_registry_repository_iam_member" "shop_synthetic_build_writer" {
  count      = var.shop_observability_enabled ? 1 : 0
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.shop_synthetic[0].name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.shop_synthetic["build"].email}"
}

resource "google_cloudfunctions2_function" "shop_synthetic" {
  count       = var.shop_observability_enabled ? 1 : 0
  project     = var.project_id
  location    = var.region
  name        = "shop-dev-browse"
  description = "Bounded browse, product and empty-cart checks."
  labels      = local.shop_monitor_labels

  build_config {
    runtime           = "nodejs22"
    entry_point       = "SyntheticFunction"
    service_account   = google_service_account.shop_synthetic["build"].name
    docker_repository = google_artifact_registry_repository.shop_synthetic[0].id
    source {
      storage_source {
        bucket     = google_storage_bucket.shop_synthetic_source[0].name
        object     = google_storage_bucket_object.shop_synthetic_source[0].name
        generation = google_storage_bucket_object.shop_synthetic_source[0].generation
      }
    }
  }

  service_config {
    service_account_email            = google_service_account.shop_synthetic["runtime"].email
    available_memory                 = "256Mi"
    available_cpu                    = "1"
    timeout_seconds                  = 45
    min_instance_count               = 0
    max_instance_count               = 1
    max_instance_request_concurrency = 1
    ingress_settings                 = "ALLOW_ALL"
    environment_variables = {
      OTEL_SERVICE_NAME = "shop-dev-synthetic"
      MONITOR_VERSION   = local.shop_synthetic_sha
    }
  }

  depends_on = [
    google_project_service.shop_monitoring,
    google_project_iam_member.shop_synthetic_trace,
    google_project_iam_member.shop_synthetic_build_logs,
    google_project_iam_member.shop_synthetic_build_service_usage,
    google_storage_bucket_iam_member.shop_synthetic_source_reader,
    google_project_iam_member.shop_synthetic_managed_source_reader,
    google_artifact_registry_repository_iam_member.shop_synthetic_build_writer,
  ]
}

resource "google_cloud_run_v2_service_iam_member" "shop_synthetic_invoker" {
  count    = var.shop_observability_enabled ? 1 : 0
  project  = var.project_id
  location = var.region
  name     = google_cloudfunctions2_function.shop_synthetic[0].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.shop_monitoring[0].email}"
}

resource "google_cloudfunctions2_function_iam_member" "shop_synthetic_metadata" {
  count          = var.shop_observability_enabled ? 1 : 0
  project        = var.project_id
  location       = var.region
  cloud_function = google_cloudfunctions2_function.shop_synthetic[0].name
  role           = "roles/cloudfunctions.viewer"
  member         = "serviceAccount:${google_project_service_identity.shop_monitoring[0].email}"
}

resource "google_monitoring_uptime_check_config" "shop_https" {
  count            = local.shop_monitor_schedule ? 1 : 0
  project          = var.project_id
  display_name     = "Online Shop dev HTTPS"
  timeout          = "10s"
  period           = "60s"
  selected_regions = ["USA", "EUROPE", "ASIA_PACIFIC"]
  user_labels      = local.shop_monitor_labels
  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.project_id, host = local.shop_hostname }
  }
  http_check {
    path         = "/_healthz"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    accepted_response_status_codes { status_value = 200 }
  }
  content_matchers {
    content = "ok"
    matcher = "CONTAINS_STRING"
  }
}

resource "google_monitoring_uptime_check_config" "shop_synthetic" {
  count        = local.shop_monitor_schedule ? 1 : 0
  project      = var.project_id
  display_name = "Online Shop dev browse journey"
  timeout      = "60s"
  period       = "300s"
  user_labels  = local.shop_monitor_labels
  synthetic_monitor {
    cloud_function_v2 { name = google_cloudfunctions2_function.shop_synthetic[0].id }
  }
  depends_on = [
    google_cloud_run_v2_service_iam_member.shop_synthetic_invoker,
    google_cloudfunctions2_function_iam_member.shop_synthetic_metadata,
  ]
}

resource "google_monitoring_alert_policy" "shop_checks" {
  for_each = local.shop_monitor_schedule ? {
    synthetic = { id = google_monitoring_uptime_check_config.shop_synthetic[0].uptime_check_id, resource = "cloud_run_revision", failures = 0, duration = "0s", absent = "900s" }
    https     = { id = google_monitoring_uptime_check_config.shop_https[0].uptime_check_id, resource = "uptime_url", failures = 1, duration = "120s", absent = "300s" }
  } : {}
  project               = var.project_id
  display_name          = "Online Shop dev ${each.key} failure or missing results"
  enabled               = true
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.shop_operator[0].name]
  severity              = "ERROR"
  user_labels           = local.shop_monitor_labels
  documentation {
    mime_type = "text/markdown"
    content   = "Inspect the exact check ID, function execution and Cloud Armor verdict. Follow https://github.com/DimitryZH/secure-delivery-platform/blob/main/monitoring/online-shop/incident-runbook.md . A missing result requires monitoring diagnosis. Confirm success samples before declaring recovery."
  }
  conditions {
    display_name = "Observed ${each.key} check failure"
    condition_threshold {
      filter          = "resource.type=\"${each.value.resource}\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"${each.value.id}\""
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.failures
      duration        = each.value.duration
      aggregations {
        alignment_period     = each.key == "synthetic" ? "300s" : "60s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
      }
      trigger { count = 1 }
    }
  }
  conditions {
    display_name = "No ${each.key} results"
    condition_absent {
      filter   = "resource.type=\"${each.value.resource}\" AND metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND metric.labels.check_id=\"${each.value.id}\""
      duration = each.value.absent
      aggregations {
        alignment_period     = each.key == "synthetic" ? "300s" : "60s"
        per_series_aligner   = "ALIGN_COUNT"
        cross_series_reducer = "REDUCE_SUM"
      }
      trigger { count = 1 }
    }
  }
}

resource "google_monitoring_alert_policy" "shop_frontend_errors" {
  count                 = var.shop_observability_enabled ? 1 : 0
  project               = var.project_id
  display_name          = "Online Shop dev observed frontend server error"
  enabled               = var.shop_observability_schedule_enabled
  combiner              = "OR"
  notification_channels = [google_monitoring_notification_channel.shop_operator[0].name]
  severity              = "WARNING"
  user_labels           = local.shop_monitor_labels
  documentation {
    mime_type = "text/markdown"
    content   = "An observed non-health frontend server error occurred in the five-minute window. This condition can persist after a single error. Use the service/environment/version/release labels and the #111 dashboard, then follow monitoring/online-shop/incident-runbook.md. Missing traffic does not prove health."
  }
  conditions {
    display_name = "Positive non-health frontend error rate"
    condition_prometheus_query_language {
      query               = trimspace(templatefile("${path.module}/../../monitoring/online-shop/frontend-errors.promql.tftpl", { project_id = var.project_id, cluster = var.gke_cluster_name, location = var.gke_location }))
      duration            = "60s"
      evaluation_interval = "30s"
    }
  }
}

output "shop_observability" {
  value = {
    provisioned        = var.shop_observability_enabled
    scheduled          = local.shop_monitor_schedule
    function           = try(google_cloudfunctions2_function.shop_synthetic[0].name, null)
    https_check        = try(google_monitoring_uptime_check_config.shop_https[0].name, null)
    synthetic_check    = try(google_monitoring_uptime_check_config.shop_synthetic[0].name, null)
    operator_channel   = try(google_monitoring_notification_channel.shop_operator[0].name, null)
    application_policy = try(google_monitoring_alert_policy.shop_frontend_errors[0].name, null)
  }
}
