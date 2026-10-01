#!/usr/bin/env python3
"""Validate initial release metadata locally; emit one JSON result to stdout."""

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

FIELDS = ("source_repository", "commit_sha", "build_id", "build_service_account",
          "image_uri", "image_digest")
DIGEST = r"sha256:[0-9a-f]{64}"
REGISTRY = r"[a-z][a-z0-9-]*-docker\.pkg\.dev/[a-z][a-z0-9-]*/[a-z][a-z0-9_-]*"
IMAGE = r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def verify(metadata, approved_registry):
    errors, identity = [], {}
    if not re.fullmatch(REGISTRY, approved_registry):
        errors.append("invalid_approved_registry")
    if not isinstance(metadata, dict):
        return {}, errors + ["metadata_must_be_object"]
    for field in FIELDS:
        value = metadata.get(field)
        if not isinstance(value, str) or not value or value.strip() != value or any(
            ord(character) < 32 for character in value
        ):
            errors.append("invalid_" + field)
        else:
            identity[field] = value
    patterns = {
        "source_repository": r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+",
        "commit_sha": r"[0-9a-f]{40}",
        "build_id": r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}",
        "build_service_account": r"[a-z0-9-]+@[a-z][a-z0-9-]*\.iam\.gserviceaccount\.com",
        "image_digest": DIGEST,
    }
    for field, pattern in patterns.items():
        if field in identity and not re.fullmatch(pattern, identity[field]):
            errors.append("invalid_" + field)
    match = re.fullmatch(
        re.escape(approved_registry) + "/(" + IMAGE + r")(?::([\w][\w.-]{0,127})|@(" + DIGEST + "))",
        identity.get("image_uri", ""), flags=re.ASCII,
    )
    if not match:
        errors.append("invalid_or_unapproved_image_uri")
    elif match.group(3) and match.group(3) != identity.get("image_digest"):
        errors.append("image_digest_mismatch")
    elif not errors:
        identity["artifact_identity"] = approved_registry + "/" + match.group(1) + "@" + identity["image_digest"]
    return identity, errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--approved-registry", required=True)
    args = parser.parse_args()
    try:
        metadata = json.loads(Path(args.metadata).read_text(encoding="utf-8"),
                              object_pairs_hook=unique_object)
    except (OSError, ValueError, UnicodeError):
        identity, errors = {}, ["unreadable_or_malformed_metadata"]
    else:
        identity, errors = verify(metadata, args.approved_registry)
    result = {
        **identity,
        "verification_status": "failed" if errors else "passed",
        "verification_timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "errors": errors,
    }
    print(json.dumps(result, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
