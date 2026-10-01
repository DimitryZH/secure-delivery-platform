"""Offline integration tests for the executable verification gate."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "cloudbuild/scripts/verify-release-metadata.py"
REGISTRY = "us-central1-docker.pkg.dev/example-project/secure-delivery"
DIGEST = "sha256:" + "a" * 64
VALID = {
    "source_repository": "DimitryZH/secure-delivery-platform",
    "commit_sha": "0123456789abcdef" * 2 + "01234567",
    "build_id": "11111111-2222-3333-4444-555555555555",
    "build_service_account": "secure-delivery-build@example-project.iam.gserviceaccount.com",
    "image_uri": REGISTRY + "/sample-service:abc123",
    "image_digest": DIGEST,
}


class VerificationTest(unittest.TestCase):
    def run_gate(self, content, registry=REGISTRY, passed=False):
        with tempfile.TemporaryDirectory() as directory:
            metadata = Path(directory) / "metadata.json"
            if content is not None:
                metadata.write_text(content, encoding="utf-8")
            completed = subprocess.run(
                [sys.executable, str(SCRIPT), "--metadata", str(metadata),
                 "--approved-registry", registry], capture_output=True, text=True,
            )
        self.assertEqual(completed.returncode, 0 if passed else 1, completed.stderr)
        result = json.loads(completed.stdout)
        self.assertEqual(result["verification_status"], "passed" if passed else "failed")
        datetime.fromisoformat(result["verification_timestamp"].replace("Z", "+00:00"))
        self.assertEqual(bool(result["errors"]), not passed)
        self.assertNotIn("trust_signal_ref", result)
        if passed:
            self.assertEqual(result["artifact_identity"], REGISTRY + "/sample-service@" + DIGEST)
        else:
            self.assertNotIn("artifact_identity", result)
        return result

    def test_tag_and_digest_inputs(self):
        for uri in (VALID["image_uri"], REGISTRY + "/sample-service@" + DIGEST):
            with self.subTest(uri=uri):
                self.run_gate(json.dumps({**VALID, "image_uri": uri}), passed=True)

    def test_each_required_field(self):
        for field in VALID:
            missing = {key: value for key, value in VALID.items() if key != field}
            for record in (missing, *({**VALID, field: value} for value in (None, 3, {}, "", " x ", "x\n"))):
                with self.subTest(field=field, record=record):
                    self.run_gate(json.dumps(record))

    def test_malformed_input(self):
        for content in (None, "", "{", "[]", "null", '{"build_id":"a","build_id":"b"}'):
            with self.subTest(content=content):
                self.run_gate(content)

    def test_invalid_identities(self):
        cases = {
            "source_repository": ["repository"],
            "commit_sha": ["main", "a" * 39, "A" * 40],
            "build_id": ["build"],
            "build_service_account": ["user@example.com"],
            "image_digest": ["latest", "sha256:" + "a" * 63, "sha256:" + "A" * 64],
            "image_uri": [
                REGISTRY.replace("us-central1", "europe-west1") + "/sample-service:tag",
                REGISTRY.replace("example-project", "other-project") + "/sample-service:tag",
                REGISTRY + "-evil/sample-service:tag",
                "https://" + REGISTRY + "/sample-service:tag",
                REGISTRY + "/sample-service",
                REGISTRY + "/../sample-service:tag",
                REGISTRY + "/sample-service@sha256:" + "b" * 64,
                REGISTRY + "/sample-service@latest",
            ],
        }
        for field, values in cases.items():
            for value in values:
                with self.subTest(field=field, value=value):
                    self.run_gate(json.dumps({**VALID, field: value}))

    def test_invalid_policy_and_untrusted_status(self):
        self.run_gate(json.dumps(VALID), registry="")
        self.run_gate(json.dumps({"verification_status": "passed", "artifact_identity": "fake"}))

    def test_repository_build_configuration(self):
        config = (ROOT / "cloudbuild/cloudbuild-verify.yaml").read_text()
        for value in ("entrypoint: 'python'", "cloudbuild/scripts/verify-release-metadata.py",
                      "--metadata", "${_METADATA_FILE}", "--approved-registry",
                      "${_LOCATION}-docker.pkg.dev/$PROJECT_ID/${_REPOSITORY}"):
            self.assertIn(value, config)
        self.assertNotIn("placeholder", config)


if __name__ == "__main__":
    unittest.main()
