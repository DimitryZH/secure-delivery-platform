#!/usr/bin/env python3
"""Reverify a candidate, sign its immutable identity, and inspect the occurrence."""

import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.request


def run_json(command):
    completed = subprocess.run(command, check=True, capture_output=True, text=True)
    return json.loads(completed.stdout)


def request_json(url, token, body=None):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        result = json.load(response)
    if not isinstance(result, dict):
        raise ValueError("invalid_api_response")
    return result


def validate_signature(occurrence, attestor, token):
    response = request_json(
        "https://binaryauthorization.googleapis.com/v1/" + attestor + ":validateAttestationOccurrence",
        token, {"attestation": occurrence["attestation"],
                "occurrenceNote": occurrence["noteName"],
                "occurrenceResourceUri": occurrence["resourceUri"]},
    )
    if response.get("result") != "VERIFIED":
        raise ValueError("signature_not_verified")


def sign_and_create(artifact, project, attestor, note, key_version, token):
    reference, digest = artifact.split("@")
    payload = json.dumps({"critical": {
        "identity": {"docker-reference": reference},
        "image": {"docker-manifest-digest": digest},
        "type": "Google Cloud BinAuthz container signature",
    }}, sort_keys=True).encode()
    signed = request_json(
        "https://cloudkms.googleapis.com/v1/" + key_version + ":asymmetricSign",
        token, {"digest": {"sha256": base64.b64encode(hashlib.sha256(payload).digest()).decode()}},
    )
    if signed.get("name") != key_version or not signed.get("signature"):
        raise ValueError("invalid_kms_signing_response")
    occurrence = {
        "resourceUri": artifact, "noteName": note,
        "attestation": {"serializedPayload": base64.b64encode(payload).decode(),
                        "signatures": [{"publicKeyId": key_version, "signature": signed["signature"]}]},
    }
    # Require an explicit VERIFIED response before writing any occurrence.
    validate_signature(occurrence, attestor, token)
    return request_json(
        "https://containeranalysis.googleapis.com/v1/projects/" + project + "/occurrences",
        token, occurrence,
    )


def inspect_occurrence(occurrences, artifact, key_version, note):
    """Find the exact subject/key/note; listing alone is not signature validation."""
    if not isinstance(occurrences, list):
        raise ValueError("invalid_occurrence_list")
    for occurrence in occurrences:
        if not isinstance(occurrence, dict):
            raise ValueError("invalid_occurrence")
        if occurrence.get("resourceUri", "").removeprefix("https://") != artifact:
            continue
        if occurrence.get("noteName") != note:
            continue
        attestation = occurrence.get("attestation", {})
        signatures = attestation.get("signatures", [])
        if not any(s.get("publicKeyId") == key_version and s.get("signature") for s in signatures):
            continue
        payload = json.loads(base64.b64decode(attestation["serializedPayload"], validate=True))
        reference, digest = artifact.split("@")
        critical = payload.get("critical", {})
        if (critical.get("identity", {}).get("docker-reference") == reference
                and critical.get("image", {}).get("docker-manifest-digest") == digest
                and critical.get("type") == "Google Cloud BinAuthz container signature"
                and occurrence.get("name")):
            return occurrence["name"]
    raise ValueError("matching_attestation_not_found")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--approved-registry", required=True)
    parser.add_argument("--project", required=True)
    parser.add_argument("--attestor", required=True)
    parser.add_argument("--note", required=True)
    parser.add_argument("--key-version", required=True)
    parser.add_argument("--inspect-only", action="store_true")
    args = parser.parse_args()
    result = {"attestation_status": "failed"}
    try:
        # No caller-provided verification result is consumed. Verification runs
        # in this trusted signing execution, before any gcloud invocation.
        verification = run_json([
            sys.executable, str(Path(__file__).with_name("verify-release-metadata.py")),
            "--metadata", args.metadata, "--approved-registry", args.approved_registry,
        ])
        if verification.get("verification_status") != "passed" or verification.get("errors") != []:
            raise ValueError("verification_not_passed")
        artifact = verification["artifact_identity"]
        result.update(artifact_identity=artifact, verification=verification)
        attestor = "projects/" + args.project + "/attestors/" + args.attestor
        token = subprocess.run(
            ["gcloud", "auth", "print-access-token", "--quiet"],
            check=True, capture_output=True, text=True,
        ).stdout.strip()
        if not token:
            raise ValueError("missing_access_token")
        if not args.inspect_only:
            created = sign_and_create(artifact, args.project, attestor, args.note, args.key_version, token)
            occurrences = [request_json(
                "https://containeranalysis.googleapis.com/v1/" + created["name"], token,
            )]
        else:
            occurrences = run_json([
                "gcloud", "container", "binauthz", "attestations", "list",
                "--project=" + args.project, "--artifact-url=" + artifact,
                "--attestor=" + args.attestor, "--attestor-project=" + args.project,
                "--format=json", "--quiet",
            ])
        reference = inspect_occurrence(occurrences, artifact, args.key_version, args.note)
        selected = next(item for item in occurrences if item["name"] == reference)
        validate_signature(selected, attestor, token)
        result.update(attestation_status="inspected" if args.inspect_only else "created",
                      trust_signal_ref=reference)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.CalledProcessError) as error:
        result["error"] = str(error)
        print(json.dumps(result, sort_keys=True))
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
