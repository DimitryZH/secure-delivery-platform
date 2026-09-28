#!/usr/bin/env bash

set -euo pipefail

test_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$test_dir/../.." && pwd)"
foundation_dir="$repository_root/terraform/foundation"
trigger_file="$foundation_dir/cloudbuild.tf"

fail_test() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_exact_line() {
  local expected="$1"
  grep -Fxq -- "$expected" "$trigger_file" || fail_test "expected line was not found: $expected"
}

[[ -f "$trigger_file" ]] || fail_test "Cloud Build trigger configuration was not found"

assert_exact_line 'resource "google_cloudbuild_trigger" "sample_service_image" {'
assert_exact_line '  project     = var.project_id'
assert_exact_line '  location    = var.region'
assert_exact_line '  name        = "sample-service-image-build"'
assert_exact_line '  filename        = "cloudbuild/cloudbuild-ci.yaml"'
assert_exact_line '  service_account = google_service_account.build.id'
assert_exact_line '    "app/sample-service/**",'
assert_exact_line '    "cloudbuild/cloudbuild-ci.yaml",'
assert_exact_line '    repository = "projects/${var.project_id}/locations/${var.region}/connections/secure-delivery-github/repositories/secure-delivery-platform"'
assert_exact_line '      branch = "^main$"'
assert_exact_line '    _LOCATION   = var.region'
assert_exact_line '    _REPOSITORY = google_artifact_registry_repository.release_images.repository_id'
assert_exact_line '  depends_on = [google_project_iam_member.build_cloud_build_builder]'

trigger_count=0
while IFS= read -r _; do
  trigger_count=$((trigger_count + 1))
done < <(grep -h -- '^resource "google_cloudbuild_trigger"' "$foundation_dir"/*.tf || true)
[[ "$trigger_count" -eq 1 ]] || fail_test "expected exactly one Cloud Build trigger resource"

if grep -Eq -- '^resource "google_cloudbuildv2_(connection|repository)"' "$foundation_dir"/*.tf; then
  fail_test "external Cloud Build source integration must not be managed here"
fi

printf 'PASS: Cloud Build trigger configuration tests\n'
