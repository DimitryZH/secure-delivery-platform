#!/usr/bin/env python3
"""Shared immutable release validation. No rendering or deployment execution."""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("verification", ROOT / "cloudbuild/scripts/verify-release-metadata.py")
verification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verification)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=verification.unique_object)


def validate(record, policy, environment, reviewed):
    if environment not in policy["environments"]:
        raise ValueError("unsupported_environment")
    if policy["environments"][environment]["namespace"] != environment:
        raise ValueError("environment_namespace_mismatch")
    identity, errors = verification.verify(record, policy["approved_registry"])
    if errors:
        raise ValueError(",".join(errors))
    if record["image_uri"] != identity["artifact_identity"]:
        raise ValueError("digest_pinned_image_required")
    if record["source_repository"] != policy["source_repository"] or record["build_service_account"] != policy["build_service_account"]:
        raise ValueError("unexpected_release_producer")
    if policy["deployment_service_account"] == policy["build_service_account"]:
        raise ValueError("deployment_authority_must_be_separate")
    if record.get("verification_status") != "passed" or record.get("errors", []) != []:
        raise ValueError("verification_not_passed")
    timestamp = record.get("verification_timestamp")
    if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
        raise ValueError("invalid_verification_timestamp")
    if datetime.fromisoformat(timestamp.removesuffix("Z") + "+00:00").tzinfo is None:
        raise ValueError("invalid_verification_timestamp")
    if not re.fullmatch(r"projects/" + re.escape(policy["project"]) + r"/occurrences/[A-Za-z0-9_-]+", record.get("trust_signal_ref", "")):
        raise ValueError("invalid_trust_signal_ref")
    if record.get("target_environment") != environment:
        raise ValueError("target_environment_mismatch")
    if policy["environments"][environment]["review_required"] and not reviewed:
        raise ValueError("environment_review_required")
    return identity
