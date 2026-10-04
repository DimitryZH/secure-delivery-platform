"""Offline checks of the Cloud Deploy bundle and its existing trust boundary."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("promotion", ROOT / "deploy/clouddeploy/prepare-release.py")
promotion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(promotion)
POLICY = promotion.deployment.load(ROOT / "deploy/environments.json")
example_text = (ROOT / "deploy/examples/verified-release.json").read_text()
for placeholder, field in (("build_service_account", "build_service_account"),
                           ("approved_registry", "approved_registry"), ("project_id", "project")):
    example_text = example_text.replace("${" + placeholder + "}", POLICY[field])
EXAMPLE = json.loads(example_text)


class CloudDeployTest(unittest.TestCase):
    def prepare(self, directory, record, reviewed=True):
        metadata = Path(directory) / "metadata.json"
        metadata.write_text(json.dumps(record))
        output = Path(directory) / "bundle"
        with patch.object(promotion.deployment, "run", side_effect=AssertionError("cloud call")):
            promotion.prepare(metadata, output, reviewed)
        return output

    def test_one_digest_and_existing_annotations_in_all_namespaces(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.prepare(directory, EXAMPLE)
            for environment in ("dev", "stage", "prod"):
                manifest = (output / "rendered" / environment / "sample-service.yaml").read_text()
                expected = promotion.deployment.render(
                    {**EXAMPLE, "target_environment": environment},
                    promotion.deployment.load(ROOT / "deploy/environments.json"), environment)
                self.assertEqual(manifest, expected)
                self.assertIn(EXAMPLE["image_uri"], manifest)
                self.assertIn('namespace: "' + environment + '"', manifest)
                self.assertIn('target-environment: "' + environment + '"', manifest)
                self.assertNotIn("LoadBalancer", manifest)
                self.assertNotIn("kind: Ingress", manifest)
            configuration = (output / "skaffold.yaml").read_text()
            self.assertNotIn("build:", configuration)
            for environment in ("dev", "stage", "prod"):
                self.assertIn("rendered/" + environment + "/sample-service.yaml", configuration)

    def test_rejects_untrusted_tagged_wrong_target_and_unreviewed_input(self):
        for mutation, reviewed in (({"image_uri": "sample-service:latest"}, True),
                                   ({"verification_status": "failed"}, True),
                                   ({"trust_signal_ref": ""}, True),
                                   ({"target_environment": "other"}, True), ({}, False)):
            with self.subTest(mutation=mutation, reviewed=reviewed), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    self.prepare(directory, {**EXAMPLE, **mutation}, reviewed)
                self.assertFalse((Path(directory) / "bundle").exists())

    def test_does_not_overwrite_an_existing_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = self.prepare(directory, EXAMPLE)
            before = (output / "skaffold.yaml").read_bytes()
            with self.assertRaisesRegex(ValueError, "output_directory_must_not_exist"):
                self.prepare(directory, EXAMPLE)
            self.assertEqual((output / "skaffold.yaml").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
