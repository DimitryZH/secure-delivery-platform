#!/usr/bin/env bash

set -euo pipefail

test_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$test_dir/../.." && pwd)"
metadata_script="$repository_root/cloudbuild/scripts/emit-release-metadata.sh"
temporary_root="$(mktemp -d)"
stub_directory="$temporary_root/bin"
command_log="$temporary_root/commands.log"
output_file="$temporary_root/output.log"
attempt_file="$temporary_root/attempts.log"

cleanup() {
  rm -rf -- "$temporary_root"
}
trap cleanup EXIT

mkdir -p -- "$stub_directory"
: > "$command_log"

cat > "$stub_directory/gcloud" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
attempt=0
if [[ -s "$ATTEMPT_FILE" ]]; then
  read -r attempt < "$ATTEMPT_FILE"
fi
attempt=$((attempt + 1))
printf '%d\n' "$attempt" > "$ATTEMPT_FILE"
printf 'gcloud' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
if ((attempt <= TEST_FAILURES_BEFORE_SUCCESS)); then
  printf 'temporary digest lookup failure\n' >&2
  exit 1
fi
printf '%s\n' "$TEST_DIGEST"
EOF

cat > "$stub_directory/sleep" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'sleep %s\n' "$1" >> "$COMMAND_LOG"
EOF

chmod +x "$stub_directory/gcloud" "$stub_directory/sleep"

fail_test() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

run_metadata() {
  local digest="$1"
  local failures_before_success="${2:-0}"
  : > "$command_log"
  printf '0\n' > "$attempt_file"
  PATH="$stub_directory:$PATH" \
    COMMAND_LOG="$command_log" \
    ATTEMPT_FILE="$attempt_file" \
    TEST_DIGEST="$digest" \
    TEST_FAILURES_BEFORE_SUCCESS="$failures_before_success" \
    PROJECT_ID="example-project" \
    SOURCE_REPOSITORY="DimitryZH/secure-delivery-platform" \
    COMMIT_SHA="0123456789abcdef0123456789abcdef01234567" \
    BUILD_ID="11111111-2222-3333-4444-555555555555" \
    BUILD_SERVICE_ACCOUNT="secure-delivery-build@example-project.iam.gserviceaccount.com" \
    IMAGE_URI="us-central1-docker.pkg.dev/example-project/secure-delivery/sample-service:0123456789abcdef0123456789abcdef01234567" \
    bash "$metadata_script"
}

valid_digest="sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
run_metadata "$valid_digest" > "$output_file"

expected_output='{"source_repository":"DimitryZH/secure-delivery-platform","commit_sha":"0123456789abcdef0123456789abcdef01234567","build_id":"11111111-2222-3333-4444-555555555555","build_service_account":"secure-delivery-build@example-project.iam.gserviceaccount.com","image_uri":"us-central1-docker.pkg.dev/example-project/secure-delivery/sample-service:0123456789abcdef0123456789abcdef01234567","image_digest":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}'
[[ "$(<"$output_file")" == "$expected_output" ]] || fail_test "release metadata JSON did not match the expected record"

expected_command='gcloud artifacts docker images describe us-central1-docker.pkg.dev/example-project/secure-delivery/sample-service:0123456789abcdef0123456789abcdef01234567 --project=example-project --format=value(image_summary.digest)'
grep -Fxq -- "$expected_command" "$command_log" || fail_test "published image digest lookup was not invoked"

run_metadata "$valid_digest" 1 > "$output_file"
[[ "$(<"$output_file")" == "$expected_output" ]] || fail_test "release metadata JSON was not emitted after a transient lookup failure"
[[ "$(grep -Fxc -- "$expected_command" "$command_log")" -eq 2 ]] || fail_test "digest lookup was not retried exactly once after a transient failure"
grep -Fxq -- 'sleep 2' "$command_log" || fail_test "digest lookup retry did not use the expected bounded delay"

if run_metadata "sample-service:0123456789abcdef0123456789abcdef01234567" > "$output_file" 2>&1; then
  fail_test "a tag was accepted as an immutable image digest"
fi
[[ "$(grep -Fxc -- "$expected_command" "$command_log")" -eq 5 ]] || fail_test "invalid digest lookup did not fail after the bounded attempt limit"

printf 'PASS: Cloud Build release metadata tests\n'
