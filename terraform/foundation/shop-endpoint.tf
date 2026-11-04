# Reviewed #106 proposal. Apply and public delegation require separate approval.
variable "shop_edge_enforce_evaluated_rules" {
  description = "Enable WAF/rate enforcement only after reviewed preview evidence and a new full plan."
  type        = bool
  default     = false
}

locals {
  shop_hostname = "shop.runtimeplatforms.dev"
}

resource "google_project_service" "shop_edge" {
  for_each           = toset(["dns.googleapis.com", "certificatemanager.googleapis.com", "compute.googleapis.com"])
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_compute_global_address" "shop_edge" {
  project      = var.project_id
  name         = "shop-dev-edge"
  address_type = "EXTERNAL"
  ip_version   = "IPV4"
  depends_on   = [google_project_service.shop_edge]
}

resource "google_dns_managed_zone" "shop_edge" {
  project     = var.project_id
  name        = "shop-dev-edge"
  dns_name    = "${local.shop_hostname}."
  description = "Only delegated shop subdomain; parent, portfolio and mail stay with existing owner."
  visibility  = "public"
  depends_on  = [google_project_service.shop_edge]
}

resource "google_certificate_manager_dns_authorization" "shop_edge" {
  project    = var.project_id
  name       = "shop-dev-edge"
  domain     = local.shop_hostname
  depends_on = [google_project_service.shop_edge]
}

resource "google_dns_record_set" "shop_certificate" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.shop_edge.name
  name         = google_certificate_manager_dns_authorization.shop_edge.dns_resource_record[0].name
  type         = google_certificate_manager_dns_authorization.shop_edge.dns_resource_record[0].type
  ttl          = 300
  rrdatas      = [google_certificate_manager_dns_authorization.shop_edge.dns_resource_record[0].data]
}

resource "google_dns_record_set" "shop_address" {
  project      = var.project_id
  managed_zone = google_dns_managed_zone.shop_edge.name
  name         = "${local.shop_hostname}."
  type         = "A"
  ttl          = 300
  rrdatas      = [google_compute_global_address.shop_edge.address]
}

resource "google_certificate_manager_certificate" "shop_edge" {
  project = var.project_id
  name    = "shop-dev-edge"
  managed {
    domains            = [local.shop_hostname]
    dns_authorizations = [google_certificate_manager_dns_authorization.shop_edge.id]
  }
  depends_on = [google_dns_record_set.shop_certificate]
}

resource "google_certificate_manager_certificate_map" "shop_edge" {
  project    = var.project_id
  name       = "shop-dev-edge"
  depends_on = [google_project_service.shop_edge]
}

resource "google_certificate_manager_certificate_map_entry" "shop_edge" {
  project      = var.project_id
  name         = "shop-dev-edge"
  map          = google_certificate_manager_certificate_map.shop_edge.name
  hostname     = local.shop_hostname
  certificates = [google_certificate_manager_certificate.shop_edge.id]
}

resource "google_compute_security_policy" "shop_edge" {
  project     = var.project_id
  name        = "shop-dev-edge"
  type        = "CLOUD_ARMOR"
  description = "Frontend only; preview WAF/rate rules before reviewed enforcement."
  rule {
    priority = 100
    action   = "deny(403)"
    match {
      expr { expression = "request.path == '/__sdp_edge_probe__'" }
    }
    description = "Deterministic bounded attachment/denial probe; no application path."
  }
  rule {
    priority = 1000
    action   = "deny(403)"
    preview  = !var.shop_edge_enforce_evaluated_rules
    match {
      expr { expression = "evaluatePreconfiguredWaf('sqli-v33-stable', {'sensitivity': 1}) || evaluatePreconfiguredWaf('xss-v33-stable', {'sensitivity': 1})" }
    }
    description = "Selected sensitivity-1 SQLi/XSS rules; evaluate checkout false positives."
  }
  rule {
    priority = 2000
    action   = "throttle"
    preview  = !var.shop_edge_enforce_evaluated_rules
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = 1200
        interval_sec = 60
      }
    }
  }
  rule {
    priority = 2147483647
    action   = "allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config { src_ip_ranges = ["*"] }
    }
  }
  depends_on = [google_project_service.shop_edge]
}

output "shop_edge_operator" {
  description = "Public child-zone delegation only; not parent DNS automation."
  value = {
    hostname                 = local.shop_hostname
    address                  = google_compute_global_address.shop_edge.address
    delegated_zone           = google_dns_managed_zone.shop_edge.dns_name
    name_servers             = google_dns_managed_zone.shop_edge.name_servers
    certificate              = google_certificate_manager_certificate.shop_edge.id
    certificate_map          = google_certificate_manager_certificate_map.shop_edge.name
    security_policy          = google_compute_security_policy.shop_edge.name
    evaluated_rules_enforced = var.shop_edge_enforce_evaluated_rules
  }
}
resource "google_compute_ssl_policy" "shop_edge" {
  project         = var.project_id
  name            = "shop-dev-edge"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
  depends_on      = [google_project_service.shop_edge]
}
