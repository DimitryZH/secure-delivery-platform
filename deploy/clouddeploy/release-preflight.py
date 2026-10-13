#!/usr/bin/env python3
"""Evaluate a fresh, independently collected release decision evidence snapshot.

This command only reads a local JSON file. It never invokes gcloud, kubectl, or a
deployment command. Its result is eligibility information, not authorization.
"""

import argparse
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("deployment", ROOT / "deploy/deploy-release.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)

TARGETS = ("dev", "stage", "prod")
MAX_AGE = timedelta(minutes=5)
PROTECTION_MARGIN = timedelta(minutes=75)
DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
RELEASE = re.compile(r"[a-z][a-z0-9-]{0,62}\Z")
SHA256 = re.compile(r"[0-9a-f]{64}\Z")


def utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("invalid_utc_timestamp")
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    if parsed.utcoffset() != timedelta(0):
        raise ValueError("invalid_utc_timestamp")
    return parsed


def object_at(parent, key):
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValueError("missing_or_invalid_" + key)
    return value


def list_at(parent, key):
    value = parent.get(key)
    if not isinstance(value, list):
        raise ValueError("missing_or_invalid_" + key)
    return value


def issue(issues, severity, code):
    issues.append({"severity": severity, "code": code})


def freshness(issues, section, name, now):
    if not isinstance(section.get("evidence_ref"), str) or not section["evidence_ref"].strip():
        issue(issues, "HOLD", name + "_reference_missing")
    try:
        observed = utc(section.get("observed_at"))
    except (TypeError, ValueError):
        issue(issues, "HOLD", name + "_observation_missing")
        return False
    if observed > now + timedelta(seconds=30) or now - observed > MAX_AGE:
        issue(issues, "HOLD", name + "_observation_expired")
        return False
    return True


def required_truth(issues, section, field, code, false_severity="BLOCKED"):
    if section.get(field) is True:
        return
    severity = false_severity if section.get(field) is False else "HOLD"
    issue(issues, severity, code)


def bound(issues, section, field, expected, code):
    actual = section.get(field)
    if actual is None:
        issue(issues, "HOLD", code + "_missing")
    elif actual != expected:
        issue(issues, "BLOCKED", code + "_mismatch")


def evaluate(evidence, release, target, action, digest, now=None):
    """Return a sanitized decision; malformed snapshots fail closed."""
    now = now or datetime.now(timezone.utc)
    issues = []
    if not isinstance(evidence, dict) or evidence.get("schema_version") != 1:
        raise ValueError("unsupported_evidence_schema")
    if target not in TARGETS or action not in ("promotion", "rollback"):
        raise ValueError("invalid_action_or_target")
    if not RELEASE.fullmatch(release) or not DIGEST.fullmatch(digest):
        raise ValueError("invalid_release_or_digest")
    request = object_at(evidence, "request")
    for key, value in (("release", release), ("target", target),
                       ("action", action), ("digest", digest)):
        bound(issues, request, key, value, "request_" + key)
    policy = deployment.load(ROOT / "deploy/environments.json")
    if target not in policy["environments"]:
        raise ValueError("unsupported_target")

    identity = object_at(evidence, "identity")
    freshness(issues, identity, "identity", now)
    bound(issues, identity, "release", release, "release_identity")
    bound(issues, identity, "digest", digest, "release_digest")
    metadata = object_at(identity, "metadata")
    metadata_identity, metadata_errors = deployment.verification.verify(
        metadata, policy["approved_registry"])
    if metadata_errors or metadata.get("image_uri") != metadata_identity.get("artifact_identity"):
        issue(issues, "BLOCKED", "invalid_immutable_metadata")
    if metadata.get("image_digest") != digest:
        issue(issues, "BLOCKED", "metadata_digest_mismatch")
    trust_ref = metadata.get("trust_signal_ref")
    if not isinstance(trust_ref, str) or not re.fullmatch(
            r"projects/" + re.escape(policy["project"]) + r"/occurrences/[A-Za-z0-9_-]+",
            trust_ref):
        issue(issues, "BLOCKED", "invalid_trust_reference")
    if (metadata.get("source_repository") != policy["source_repository"]
            or metadata.get("build_service_account") != policy["build_service_account"]):
        issue(issues, "BLOCKED", "unexpected_release_producer")
    if policy["build_service_account"] == policy["deployment_service_account"]:
        issue(issues, "BLOCKED", "authority_separation_missing")
    required_truth(issues, identity, "release_annotations_match", "release_annotations_conflict")
    required_truth(issues, identity, "render_succeeded", "release_render_incomplete")

    build = object_at(evidence, "build")
    freshness(issues, build, "build", now)
    bound(issues, build, "build_id", metadata.get("build_id"), "build_identity")
    bound(issues, build, "digest", digest, "build_digest")
    required_truth(issues, build, "succeeded", "producing_build_failed")
    required_truth(issues, build, "source_and_identity_match", "build_source_or_identity_conflict")
    required_truth(issues, build, "image_available", "image_unavailable")

    verification = object_at(evidence, "verification")
    freshness(issues, verification, "verification", now)
    bound(issues, verification, "digest", digest, "verification_digest")
    bound(issues, verification, "build_id", metadata.get("build_id"), "verification_build")
    required_truth(issues, verification, "trusted_result_retained", "trusted_verification_missing", "HOLD")
    required_truth(issues, verification, "passed", "verification_failed")
    if metadata.get("verification_status") != "passed" or metadata.get("errors") != []:
        issue(issues, "BLOCKED", "metadata_verification_not_passed")
    if not isinstance(metadata.get("verification_timestamp"), str):
        issue(issues, "HOLD", "verification_timestamp_missing")
    else:
        try:
            utc(metadata["verification_timestamp"])
        except ValueError:
            issue(issues, "BLOCKED", "verification_timestamp_invalid")

    attestation = object_at(evidence, "attestation")
    freshness(issues, attestation, "attestation", now)
    bound(issues, attestation, "digest", digest, "attestation_digest")
    bound(issues, attestation, "occurrence", metadata.get("trust_signal_ref"), "attestation_occurrence")
    required_truth(issues, attestation, "signature_verified", "attestation_invalid")
    required_truth(issues, attestation, "attestor_note_key_match", "attestor_note_or_key_mismatch")

    admission = object_at(evidence, "admission")
    freshness(issues, admission, "admission", now)
    required_truth(issues, admission, "cluster_enforced", "cluster_admission_not_enforced")
    required_truth(issues, admission, "policy_requires_attestor", "admission_policy_incompatible")
    required_truth(issues, admission, "no_bypass", "admission_bypass_detected")

    artifacts = object_at(evidence, "artifacts")
    for name in ("source", "rendered"):
        item = object_at(artifacts, name)
        freshness(issues, item, name + "_artifact", now)
        bound(issues, item, "release", release, name + "_artifact_release")
        if name == "rendered":
            bound(issues, item, "target", target, "rendered_artifact_target")
            bound(issues, item, "digest", digest, "rendered_artifact_digest")
        required_truth(issues, item, "available", name + "_artifact_unavailable")
        required_truth(issues, item, "live_generation", name + "_artifact_not_live")
        expected = item.get("expected_sha256")
        actual = item.get("actual_sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected) or actual != expected:
            issue(issues, "BLOCKED", name + "_artifact_hash_mismatch")
        if name == "source":
            bound(issues, identity, "source_archive_sha256", expected,
                  "source_archive_annotation_hash")
        try:
            expiration = utc(item.get("retention_expires_at"))
        except (TypeError, ValueError):
            issue(issues, "HOLD", name + "_retention_unverified")
        else:
            if expiration < now + PROTECTION_MARGIN:
                issue(issues, "BLOCKED", name + "_retention_insufficient")

    target_state = object_at(evidence, "target_state")
    freshness(issues, target_state, "target_state", now)
    bound(issues, target_state, "target", target, "target_state_target")
    bound(issues, target_state, "namespace", target, "target_namespace")
    bound(issues, target_state, "deployment_authority",
          policy["deployment_service_account"], "target_deployment_authority")
    bound(issues, target_state, "approval_required",
          policy["environments"][target]["review_required"], "target_approval_requirement")
    required_truth(issues, target_state, "release_snapshot_matches_current",
                   "target_snapshot_drift")
    required_truth(issues, target_state, "deployment_authority_matches",
                   "target_deployment_authority_mismatch")
    required_truth(issues, target_state, "approval_gate_matches_policy",
                   "target_approval_gate_mismatch")
    required_truth(issues, target_state, "namespace_and_digest_match",
                   "target_render_incompatible")
    required_truth(issues, target_state, "target_render_succeeded",
                   "target_render_incomplete")

    rollouts = object_at(evidence, "rollouts")
    freshness(issues, rollouts, "rollouts", now)
    required_truth(issues, rollouts, "no_active_or_queued_conflict", "conflicting_rollout")

    caller = object_at(evidence, "caller")
    freshness(issues, caller, "caller", now)
    expected_permission = ("clouddeploy.rollouts.create" if action == "promotion"
                           else "clouddeploy.rollouts.rollback")
    bound(issues, caller, "permission", expected_permission, "caller_permission")
    required_truth(issues, caller, "effective_permission", "caller_not_authorized")
    required_truth(issues, caller, "rollout_create_permission", "caller_cannot_create_rollout")
    required_truth(issues, caller, "deployment_act_as_permission", "caller_cannot_act_as_deployment_identity")

    operations = object_at(evidence, "operations")
    freshness(issues, operations, "operations", now)
    bound(issues, operations, "release", release, "operations_release")
    bound(issues, operations, "digest", digest, "operations_digest")
    required_truth(issues, operations, "review_complete", "operational_review_incomplete", "HOLD")
    decision = operations.get("decision")
    if decision == "reject":
        issue(issues, "BLOCKED", "release_review_rejected")
    elif decision != "continue":
        issue(issues, "HOLD", "release_review_not_continue")
    required_truth(issues, operations, "health_evidence_sufficient", "health_evidence_insufficient", "HOLD")
    required_truth(issues, operations, "runtime_identity_stable", "runtime_identity_changed", "HOLD")

    if action == "promotion":
        if target == "dev":
            issue(issues, "BLOCKED", "promotion_requires_stage_or_prod")
        predecessor = {"stage": "dev", "prod": "stage"}.get(target)
        if predecessor:
            bound(issues, rollouts, "successful_prior_target", predecessor, "prior_target")
            bound(issues, rollouts, "successful_prior_release", release, "prior_release")
            bound(issues, rollouts, "successful_prior_digest", digest, "prior_digest")
            required_truth(issues, rollouts, "prior_rollout_and_job_succeeded",
                           "prior_rollout_not_successful")
            required_truth(issues, rollouts, "no_target_rollout_for_release",
                           "target_already_has_rollout")
            bound(issues, operations, "reviewed_target", predecessor, "promotion_review_target")
    else:
        required_truth(issues, rollouts, "prior_target_rollout_and_job_succeeded",
                       "rollback_prior_rollout_not_successful")
        bound(issues, rollouts, "prior_target_release", release, "rollback_prior_release")
        bound(issues, rollouts, "prior_target_digest", digest, "rollback_prior_digest")
        required_truth(issues, rollouts, "previously_accepted", "rollback_release_not_accepted")
        required_truth(issues, rollouts, "earlier_than_current", "rollback_not_earlier_release")
        required_truth(issues, rollouts, "different_from_current", "rollback_already_running")
        bound(issues, operations, "reviewed_target", target, "rollback_review_target")

    severity = "BLOCKED" if any(i["severity"] == "BLOCKED" for i in issues) else (
        "HOLD" if issues else "READY")
    return {"schema_version": 1, "action": action, "target": target, "decision": severity,
            "authorization": "separate_required", "cloud_action_executed": False,
            "issues": sorted(issues, key=lambda item: (item["severity"], item["code"]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", required=True)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--action", required=True, choices=("promotion", "rollback"))
    parser.add_argument("--digest", required=True, help="Explicit immutable sha256 digest")
    parser.add_argument("--evidence", required=True, help="Fresh, independently collected JSON snapshot")
    parser.add_argument("--format", choices=("json", "text"), default="text")
    args = parser.parse_args()
    try:
        evidence = deployment.load(args.evidence)
        result = evaluate(evidence, args.release, args.target, args.action, args.digest)
    except (OSError, ValueError, TypeError, KeyError):
        result = {"schema_version": 1, "action": args.action, "target": args.target,
                  "decision": "BLOCKED", "authorization": "separate_required",
                  "cloud_action_executed": False,
                  "issues": [{"severity": "BLOCKED", "code": "malformed_or_unreadable_evidence"}]}
    if args.format == "json":
        print(json.dumps(result, sort_keys=True))
    else:
        print(result["decision"] + " — " + args.action + " to " + args.target)
        for item in result["issues"]:
            print(item["severity"] + ": " + item["code"])
        print("Separate authorization is required; no cloud action was executed.")
    return {"READY": 0, "HOLD": 2, "BLOCKED": 3}[result["decision"]]


if __name__ == "__main__":
    raise SystemExit(main())
