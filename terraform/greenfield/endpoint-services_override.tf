# Only isolated roots use this override. An API has exactly one state owner.
resource "google_project_service" "shop_edge" {
  for_each = setsubtract(toset(["dns.googleapis.com", "certificatemanager.googleapis.com", "compute.googleapis.com"]), var.enabled_services)
}
