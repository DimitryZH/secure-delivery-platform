#!/usr/bin/env bash

set -euo pipefail

test_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$test_dir/../.." && pwd)"
preflight_script="$repository_root/scripts/preflight-foundation.sh"
temporary_root="$(mktemp -d)"
stub_directory="$temporary_root/bin"
command_log="$temporary_root/commands.log"
output_file="$temporary_root/output.log"

cleanup() {
  rm -rf -- "$temporary_root"
}
trap cleanup EXIT

mkdir -p -- "$stub_directory"
: > "$command_log"

cat > "$stub_directory/git" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'git' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
[[ "${1:-}" == "diff" ]] || exit 90
EOF

cat > "$stub_directory/gcloud" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'gcloud' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"

case "$*" in
  "config get-value project --quiet")
    printf '%s\n' "$TEST_PROJECT_ID"
    ;;
  "auth list --filter=status:ACTIVE --format=value(account)")
    printf '%s\n' "operator@example.invalid"
    ;;
  "projects describe $TEST_PROJECT_ID --format=value(projectNumber)")
    printf '%s\n' "123456789012"
    ;;
  *)
    exit 91
    ;;
esac
EOF

cat > "$stub_directory/terraform" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf 'terraform' >> "$COMMAND_LOG"
printf ' %s' "$@" >> "$COMMAND_LOG"
printf '\n' >> "$COMMAND_LOG"
EOF

chmod +x "$stub_directory/git" "$stub_directory/gcloud" "$stub_directory/terraform"

fail_test() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

assert_contains() {
  local expected="$1"
  local file="$2"
  grep -Fq -- "$expected" "$file" || fail_test "expected output was not found: $expected"
}

run_preflight() {
  PATH="$stub_directory:$PATH" \
    COMMAND_LOG="$command_log" \
    TEST_PROJECT_ID="sample-project-123" \
    bash "$preflight_script" "$@"
}

run_preflight \
  --project-id sample-project-123 \
  --state-bucket-name sample-state-bucket-123 \
  --state-bucket-location US > "$output_file"

assert_contains "Foundation preflight passed." "$output_file"
assert_contains "Project ID: sample-project-123" "$output_file"
assert_contains "Project number: 123456789012" "$output_file"
assert_contains "State bucket name: sample-state-bucket-123" "$output_file"
assert_contains "State bucket location: US" "$output_file"

assert_contains "gcloud config get-value project --quiet" "$command_log"
assert_contains "gcloud auth list --filter=status:ACTIVE --format=value(account)" "$command_log"
assert_contains "gcloud projects describe sample-project-123 --format=value(projectNumber)" "$command_log"
assert_contains "terraform -chdir=terraform/bootstrap init -backend=false" "$command_log"
assert_contains "terraform -chdir=terraform/bootstrap validate" "$command_log"
assert_contains "terraform -chdir=terraform/foundation init -backend=false" "$command_log"
assert_contains "terraform -chdir=terraform/foundation validate" "$command_log"
assert_contains "terraform fmt -check -recursive terraform/bootstrap terraform/foundation" "$command_log"

if grep -Eq -- 'terraform .*(plan|apply|destroy|-migrate-state)|gcloud .*(services enable|storage buckets (create|update)|secrets|iam|set-iam-policy)' "$command_log"; then
  fail_test "a mutating command was invoked"
fi

: > "$command_log"
if run_preflight \
  --project-id replace-with-your-project-id \
  --state-bucket-name sample-state-bucket-123 \
  --state-bucket-location US > "$output_file" 2>&1; then
  fail_test "the project ID placeholder was accepted"
fi
[[ ! -s "$command_log" ]] || fail_test "a command ran before project ID placeholder rejection"

: > "$command_log"
if run_preflight \
  --project-id sample-project-123 \
  --state-bucket-name replace-with-globally-unique-state-bucket-name \
  --state-bucket-location US > "$output_file" 2>&1; then
  fail_test "the state bucket placeholder was accepted"
fi
[[ ! -s "$command_log" ]] || fail_test "a command ran before state bucket placeholder rejection"

: > "$command_log"
if run_preflight \
  --project-id INVALID_PROJECT \
  --state-bucket-name sample-state-bucket-123 \
  --state-bucket-location US > "$output_file" 2>&1; then
  fail_test "a malformed project ID was accepted"
fi
[[ ! -s "$command_log" ]] || fail_test "a command ran before malformed project ID rejection"

: > "$command_log"
if run_preflight \
  --project-id sample-project-123 \
  --state-bucket-name Invalid_Bucket_Name \
  --state-bucket-location US > "$output_file" 2>&1; then
  fail_test "a malformed state bucket name was accepted"
fi
[[ ! -s "$command_log" ]] || fail_test "a command ran before malformed state bucket name rejection"

printf 'PASS: preflight foundation tests\n'
