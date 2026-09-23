#!/usr/bin/env bash

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/preflight-foundation.sh \
    --project-id PROJECT_ID \
    --state-bucket-name STATE_BUCKET_NAME \
    --state-bucket-location STATE_BUCKET_LOCATION

Runs read-only operator context checks and local Terraform validation for the
bootstrap and foundation configurations.
EOF
}

fail() {
  printf 'Error: %s\n' "$1" >&2
  exit 1
}

project_id=""
state_bucket_name=""
state_bucket_location=""

while (( $# > 0 )); do
  case "$1" in
    --help)
      usage
      exit 0
      ;;
    --project-id)
      (( $# >= 2 )) || fail "--project-id requires a value."
      [[ -n "$2" && "$2" != --* ]] || fail "--project-id requires a value."
      [[ -z "$project_id" ]] || fail "--project-id may be specified only once."
      project_id="$2"
      shift 2
      ;;
    --state-bucket-name)
      (( $# >= 2 )) || fail "--state-bucket-name requires a value."
      [[ -n "$2" && "$2" != --* ]] || fail "--state-bucket-name requires a value."
      [[ -z "$state_bucket_name" ]] || fail "--state-bucket-name may be specified only once."
      state_bucket_name="$2"
      shift 2
      ;;
    --state-bucket-location)
      (( $# >= 2 )) || fail "--state-bucket-location requires a value."
      [[ -n "$2" && "$2" != --* ]] || fail "--state-bucket-location requires a value."
      [[ -z "$state_bucket_location" ]] || fail "--state-bucket-location may be specified only once."
      state_bucket_location="$2"
      shift 2
      ;;
    *)
      fail "unknown argument: $1"
      ;;
  esac
done

[[ -n "$project_id" ]] || fail "--project-id is required."
[[ -n "$state_bucket_name" ]] || fail "--state-bucket-name is required."
[[ -n "$state_bucket_location" ]] || fail "--state-bucket-location is required."

[[ "$project_id" != "replace-with-your-project-id" ]] || fail "--project-id must not use the example placeholder."
[[ "$project_id" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]] || fail "--project-id is not a valid Google Cloud project ID."

[[ "$state_bucket_name" != "replace-with-globally-unique-state-bucket-name" ]] || fail "--state-bucket-name must not use the example placeholder."
[[ "$state_bucket_name" =~ ^[a-z0-9][a-z0-9._-]{1,61}[a-z0-9]$ ]] || fail "--state-bucket-name is not a valid Google Cloud Storage bucket name."
[[ "$state_bucket_name" != *..* ]] || fail "--state-bucket-name must not contain consecutive periods."
[[ ! "$state_bucket_name" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]] || fail "--state-bucket-name must not use an IPv4 address format."

[[ "$state_bucket_location" != "replace-with-your-state-bucket-location" ]] || fail "--state-bucket-location must not use an example placeholder."

for required_command in terraform gcloud git; do
  command -v "$required_command" >/dev/null 2>&1 || fail "required command not found: $required_command"
done

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "$script_dir/.." && pwd)"
cd "$repository_root"

git diff --quiet --ignore-submodules -- || fail "the Git working tree contains unstaged tracked changes."
git diff --cached --quiet --ignore-submodules -- || fail "the Git working tree contains staged tracked changes."

if ! active_project="$(gcloud config get-value project --quiet 2>/dev/null)"; then
  fail "unable to read the active gcloud project."
fi
[[ -n "$active_project" && "$active_project" != "(unset)" ]] || fail "no active gcloud project is configured."
[[ "$active_project" == "$project_id" ]] || fail "the active gcloud project does not match --project-id."

if ! active_account="$(gcloud auth list --filter=status:ACTIVE '--format=value(account)' 2>/dev/null)"; then
  fail "unable to read the active gcloud account."
fi
[[ -n "$active_account" ]] || fail "no active gcloud account is available."

if ! project_number="$(gcloud projects describe "$project_id" '--format=value(projectNumber)' 2>/dev/null)"; then
  fail "the active account cannot describe the requested project."
fi
[[ "$project_number" =~ ^[0-9]+$ ]] || fail "the project access check returned an invalid project number."

terraform -chdir=terraform/bootstrap init -backend=false
terraform -chdir=terraform/bootstrap validate
terraform -chdir=terraform/foundation init -backend=false
terraform -chdir=terraform/foundation validate
terraform fmt -check -recursive terraform/bootstrap terraform/foundation

printf '\nFoundation preflight passed.\n'
printf 'Project ID: %s\n' "$project_id"
printf 'Project number: %s\n' "$project_number"
printf 'State bucket name: %s\n' "$state_bucket_name"
printf 'State bucket location: %s\n' "$state_bucket_location"
