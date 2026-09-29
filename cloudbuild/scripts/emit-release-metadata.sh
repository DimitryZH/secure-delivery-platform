#!/usr/bin/env bash

set -euo pipefail

for variable_name in \
  PROJECT_ID \
  SOURCE_REPOSITORY \
  COMMIT_SHA \
  BUILD_ID \
  BUILD_SERVICE_ACCOUNT \
  IMAGE_URI; do
  [[ -n "${!variable_name:-}" ]] || {
    printf 'Error: required build context is missing: %s\n' "$variable_name" >&2
    exit 1
  }
done

command -v gcloud >/dev/null 2>&1 || {
  printf 'Error: required command not found: gcloud\n' >&2
  exit 1
}

image_digest="$(
  gcloud artifacts docker images describe "$IMAGE_URI" \
    --project="$PROJECT_ID" \
    --format='value(image_summary.digest)'
)"

[[ "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  printf 'Error: published image did not return a valid sha256 digest.\n' >&2
  exit 1
}

printf '{"source_repository":"%s","commit_sha":"%s","build_id":"%s","build_service_account":"%s","image_uri":"%s","image_digest":"%s"}\n' \
  "$SOURCE_REPOSITORY" \
  "$COMMIT_SHA" \
  "$BUILD_ID" \
  "$BUILD_SERVICE_ACCOUNT" \
  "$IMAGE_URI" \
  "$image_digest"
