#!/usr/bin/env bash

set -euo pipefail

test_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$test_dir/../.." && pwd)"
config_file="$repository_root/cloudbuild/cloudbuild-ci.yaml"
expected_image='${_LOCATION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}/sample-service:$COMMIT_SHA'

fail_test() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_exact_line() {
  local expected="$1"
  grep -Fxq -- "$expected" "$config_file" || fail_test "expected line was not found: $expected"
}

[[ -f "$config_file" ]] || fail_test "Cloud Build configuration was not found"

assert_exact_line "substitutions:"
assert_exact_line "  _LOCATION: us-central1"
assert_exact_line "  _REPOSITORY: secure-delivery"
assert_exact_line "    args: ['build', '-t', '$expected_image', '.']"
assert_exact_line "  - '$expected_image'"
assert_exact_line "options:"
assert_exact_line "  logging: CLOUD_LOGGING_ONLY"
assert_exact_line "    dir: 'app/sample-service'"

config_content="$(<"$config_file")"
identity_count=0
remaining_content="$config_content"
while [[ "$remaining_content" == *"$expected_image"* ]]; do
  remaining_content="${remaining_content#*"$expected_image"}"
  identity_count=$((identity_count + 1))
done
[[ "$identity_count" -eq 2 ]] || fail_test "expected image identity must appear exactly twice"

[[ "$config_content" != *'LOCATION-docker.pkg.dev'* ]] || fail_test "legacy LOCATION placeholder remains"
[[ "$config_content" != *'PROJECT_ID/REPOSITORY'* ]] || fail_test "legacy project/repository placeholders remain"

content_without_repository_substitution="${config_content//_REPOSITORY/}"
[[ "$content_without_repository_substitution" != *'REPOSITORY'* ]] || fail_test "unexpanded REPOSITORY placeholder remains"

printf 'PASS: Cloud Build CI configuration tests\n'
