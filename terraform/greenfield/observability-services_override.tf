# Keep APIs already owned by required[] out of this optional ownership set.
resource "google_project_service" "shop_monitoring" {
  for_each = var.shop_observability_enabled ? setsubtract(toset(["cloudfunctions.googleapis.com", "run.googleapis.com", "pubsub.googleapis.com"]), var.enabled_services) : toset([])
}
