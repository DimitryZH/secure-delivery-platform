"""Offline gate and API contract tests; no GCP writes or credentials required."""

import base64
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("attest", ROOT / "cloudbuild/scripts/attest-release.py")
attest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(attest)
PROJECT = "example-project"
REGISTRY = "us-central1-docker.pkg.dev/" + PROJECT + "/secure-delivery"
DIGEST = "sha256:" + "a" * 64
ARTIFACT = REGISTRY + "/sample-service@" + DIGEST
KEY = "projects/example-project/locations/us-central1/keyRings/secure-delivery-attestation/cryptoKeys/verification/cryptoKeyVersions/1"
PUBLIC_KEY_ID = "//cloudkms.googleapis.com/v1/" + KEY
NOTE = "projects/example-project/notes/secure-delivery-verification"
METADATA = {
    "source_repository": "DimitryZH/secure-delivery-platform",
    "commit_sha": "a" * 40, "build_id": "11111111-2222-3333-4444-555555555555",
    "build_service_account": "secure-delivery-build@example-project.iam.gserviceaccount.com",
    "image_uri": REGISTRY + "/sample-service:main", "image_digest": DIGEST,
}
REAL_RUN = subprocess.run


class AttestationTest(unittest.TestCase):
    def exercise(self, metadata=METADATA, denied=False, inspect=False, missing_occurrence=False,
                 kms_denied=False, key_version=KEY, public_key_id=PUBLIC_KEY_ID, occurrence_key_id=PUBLIC_KEY_ID):
        calls, api_calls = [], []
        stored = {}

        def command(command, **kwargs):
            if command[0] != "gcloud":
                return REAL_RUN(command, **kwargs)
            calls.append(command)
            if command[1:3] == ["auth", "print-access-token"]:
                return subprocess.CompletedProcess(command, 0, "test-token\n")
            occurrence = self.occurrence()
            occurrence["attestation"]["signatures"][0]["publicKeyId"] = occurrence_key_id
            return subprocess.CompletedProcess(command, 0, json.dumps([occurrence]))

        def api(url, token, body=None):
            self.assertEqual(token, "test-token")
            api_calls.append((url, body))
            if url.endswith(":asymmetricSign"):
                if kms_denied:
                    raise PermissionError("signing_denied")
                return {"name": KEY, "signature": "c2lnbmF0dXJl"}
            if url.endswith(":validateAttestationOccurrence"):
                return {"result": "ATTESTATION_NOT_VERIFIABLE" if denied else "VERIFIED"}
            if url.endswith("/occurrences"):
                stored.update(body)
                stored["name"] = "projects/example-project/occurrences/123"
                return copy.deepcopy(stored)
            return {} if missing_occurrence else copy.deepcopy(stored)

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.json"
            if metadata is not None:
                path.write_text(json.dumps(metadata), encoding="utf-8")
            args = ["attest-release.py", "--metadata", str(path), "--approved-registry", REGISTRY,
                    "--project", PROJECT, "--attestor", "secure-delivery-verification",
                    "--note", NOTE, "--key-version", key_version, "--public-key-id", public_key_id]
            if inspect:
                args.append("--inspect-only")
            output = io.StringIO()
            with patch.object(sys, "argv", args), patch.object(attest.subprocess, "run", side_effect=command), \
                    patch.object(attest, "request_json", side_effect=api), patch.object(sys, "stdout", output):
                status = attest.main()
        return status, json.loads(output.getvalue()), calls, api_calls, stored

    def occurrence(self):
        payload = {"critical": {"identity": {"docker-reference": ARTIFACT.split("@")[0]},
                                "image": {"docker-manifest-digest": DIGEST},
                                "type": "Google Cloud BinAuthz container signature"}}
        return {"name": "projects/example-project/occurrences/123", "resourceUri": ARTIFACT,
                "noteName": NOTE, "attestation": {"serializedPayload": base64.b64encode(json.dumps(payload).encode()).decode(),
                "signatures": [{"publicKeyId": PUBLIC_KEY_ID, "signature": "c2lnbmF0dXJl"}]}}

    def test_verified_candidate_signs_exact_digest_then_validates_before_create(self):
        status, result, commands, api, stored = self.exercise()
        self.assertEqual(status, 0)
        self.assertEqual(result["attestation_status"], "created")
        self.assertEqual(result["artifact_identity"], ARTIFACT)
        self.assertEqual(result["verification"]["verification_status"], "passed")
        self.assertEqual(result["trust_signal_ref"], stored["name"])
        self.assertEqual(api[0][0], "https://cloudkms.googleapis.com/v1/" + KEY + ":asymmetricSign")
        self.assertTrue(api[1][0].endswith(":validateAttestationOccurrence"))
        self.assertTrue(api[2][0].endswith("/occurrences"))
        payload = base64.b64decode(stored["attestation"]["serializedPayload"])
        self.assertEqual(base64.b64decode(api[0][1]["digest"]["sha256"]), hashlib.sha256(payload).digest())
        self.assertEqual(stored["resourceUri"], ARTIFACT)
        self.assertEqual(stored["attestation"]["signatures"][0]["publicKeyId"], PUBLIC_KEY_ID)
        self.assertEqual(api[1][1]["attestation"]["signatures"][0]["publicKeyId"], PUBLIC_KEY_ID)

    def test_missing_failed_or_forged_verification_never_reaches_authority(self):
        for record in (None, {}, {"verification_status": "passed", "artifact_identity": ARTIFACT},
                       {**METADATA, "image_digest": "latest"},
                       {**METADATA, "image_uri": REGISTRY + "/sample-service@sha256:" + "b" * 64},
                       {**METADATA, "image_uri": "elsewhere.example/image:main"}):
            with self.subTest(record=record):
                status, result, commands, api, stored = self.exercise(metadata=record)
                self.assertEqual(status, 1)
                self.assertEqual(result["attestation_status"], "failed")
                self.assertNotIn("trust_signal_ref", result)
                self.assertEqual(commands, [])
                self.assertEqual(api, [])

    def test_signature_denial_never_creates_occurrence(self):
        status, result, _, api, stored = self.exercise(denied=True)
        self.assertEqual(status, 1)
        self.assertEqual(result["error"], "signature_not_verified")
        self.assertEqual(stored, {})
        self.assertEqual(len(api), 2)

    def test_kms_permission_denial_and_missing_readback_fail_closed(self):
        for options in ({"kms_denied": True}, {"missing_occurrence": True}):
            with self.subTest(options=options):
                status, result, _, _, _ = self.exercise(**options)
                self.assertEqual(status, 1)
                self.assertNotIn("trust_signal_ref", result)

    def test_inspection_validates_signature_without_signing_or_creating(self):
        status, result, commands, api, _ = self.exercise(inspect=True)
        self.assertEqual(status, 0)
        self.assertEqual(result["attestation_status"], "inspected")
        self.assertEqual(len(api), 1)
        self.assertTrue(api[0][0].endswith(":validateAttestationOccurrence"))
        self.assertIn("--artifact-url=" + ARTIFACT, commands[1])

    def test_readback_rejects_other_subject_note_key_or_payload(self):
        for field, value in (("resourceUri", ARTIFACT + "0"), ("noteName", NOTE + "-other"),
                             ("attestation", {})):
            record = self.occurrence()
            record[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                attest.inspect_occurrence([record], ARTIFACT, PUBLIC_KEY_ID, NOTE)
        record = self.occurrence()
        record["attestation"]["signatures"][0]["publicKeyId"] = PUBLIC_KEY_ID + "0"
        with self.assertRaises(ValueError):
            attest.inspect_occurrence([record], ARTIFACT, PUBLIC_KEY_ID, NOTE)

    def test_invalid_key_configuration_never_reaches_authority(self):
        for options in ({"public_key_id": KEY}, {"public_key_id": PUBLIC_KEY_ID + "0"},
                        {"key_version": PUBLIC_KEY_ID}, {"key_version": ""}):
            with self.subTest(options=options):
                status, result, commands, api, stored = self.exercise(**options)
                self.assertEqual(status, 1)
                self.assertNotIn("trust_signal_ref", result)
                self.assertEqual(commands, [])
                self.assertEqual(api, [])
                self.assertEqual(stored, {})

    def test_inspection_rejects_bare_resource_name_as_public_key_id(self):
        status, result, _, api, _ = self.exercise(inspect=True, occurrence_key_id=KEY)
        self.assertEqual(status, 1)
        self.assertNotIn("trust_signal_ref", result)
        self.assertEqual(api, [])

    def test_authority_configuration_is_separate(self):
        config = (ROOT / "cloudbuild/cloudbuild-attest.yaml").read_text()
        self.assertIn("secure-delivery-attestation@$PROJECT_ID", config)
        self.assertIn("cloudbuild/scripts/attest-release.py", config)
        self.assertIn("'--public-key-id'", config)
        self.assertIn("'//cloudkms.googleapis.com/v1/projects/$PROJECT_ID/", config)
        infrastructure = (ROOT / "terraform/foundation/attestation.tf").read_text()
        self.assertNotIn("google_service_account.build.email", infrastructure)
        self.assertNotIn("roles/iam.serviceAccount", infrastructure)
        self.assertNotIn('resource "google_cloudbuild_trigger"', infrastructure)
        self.assertIn("prevent_destroy = true", infrastructure)
        self.assertIn("note_reference = google_container_analysis_note.verification.id", infrastructure)


if __name__ == "__main__":
    unittest.main()
