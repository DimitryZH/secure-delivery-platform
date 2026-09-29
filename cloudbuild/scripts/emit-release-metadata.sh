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

digest_lookup_max_attempts=5
digest_lookup_retry_seconds=2
image_digest=""

for ((attempt = 1; attempt <= digest_lookup_max_attempts; attempt++)); do
  candidate_digest=""
  if candidate_digest="$(
    gcloud artifacts docker images describe "$IMAGE_URI" \
      --project="$PROJECT_ID" \
      --format='value(image_summary.digest)'
  )" && [[ "$candidate_digest" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    image_digest="$candidate_digest"
    break
  fi

  printf 'Warning: published image digest lookup attempt %d/%d did not return a valid digest.\n' \
    "$attempt" "$digest_lookup_max_attempts" >&2

  if ((attempt < digest_lookup_max_attempts)); then
    sleep "$digest_lookup_retry_seconds"
  fi
done

[[ "$image_digest" =~ ^sha256:[0-9a-f]{64}$ ]] || {
  printf 'Error: published image did not return a valid sha256 digest after %d attempts.\n' \
    "$digest_lookup_max_attempts" >&2
  exit 1
}

printf '{"source_repository":"%s","commit_sha":"%s","build_id":"%s","build_service_account":"%s","image_uri":"%s","image_digest":"%s"}\n' \
  "$SOURCE_REPOSITORY" \
  "$COMMIT_SHA" \
  "$BUILD_ID" \
  "$BUILD_SERVICE_ACCOUNT" \
  "$IMAGE_URI" \
  "$image_digest"
