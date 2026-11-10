"""Request/bootstrap regressions only; these do not execute an SDK container."""
import importlib.util
from pathlib import Path
import shlex
import unittest
from unittest.mock import patch

from release_fixtures import accepted_policy

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


r = load("dependency_catalog", "cloudbuild/online-shop/release.py")
c = load("dependency_complete", "cloudbuild/online-shop/complete.py")
collector = load("dependency_collector", "cloudbuild/online-shop/collector.py")
REV = "c" * 40


class ExecutionDependencyTests(unittest.TestCase):
    def assert_bootstrap(self, step, *, signing=False, transport=False):
        self.assertEqual(step["name"], "gcr.io/google.com/cloudsdktool/cloud-sdk:slim")
        self.assertEqual(step["entrypoint"], "bash")
        self.assertEqual(step["args"][0], "-ceu")
        script = step["args"][1]
        lines = script.splitlines()
        install = shlex.split(lines[0].split("&&", 1)[1])
        self.assertEqual(install[:2], ["apt-get", "install"])
        self.assertIn("python3", install)
        self.assertIn("git", install)
        # Dependency checks must execute before materialization or cloud reads.
        for tool in ("git", "python3", *(("gcloud",) if signing else ()), *(("sha256sum",) if transport else ())):
            self.assertIn("command -v " + tool + " >/dev/null", lines[1])
        self.assertTrue(any(line.startswith("python3 ") for line in lines[2:]))

    def test_catalog_bootstraps_python_before_materialization_and_signing(self):
        p = r.policy()
        build = r.build_request(p, REV, {"components": [{"inputs": []}]})
        self.assert_bootstrap(build["steps"][0])
        self.assertEqual(build["timeout"], "1200s")
        self.assertEqual(build["source"]["gitSource"]["revision"], REV)
        self.assertEqual(build["serviceAccount"], p["producer"])
        self.assertIn("SOURCE_REVISION=" + r.REVISION, build["steps"][1]["args"])
        signing = r.signing_request(p, REV, "gs://" + p["project"] + "-attestation-source/catalog/candidate.json#123", "sha256:" + "a" * 64)
        self.assert_bootstrap(signing["steps"][0], signing=True, transport=True)
        self.assertEqual(signing["timeout"], "600s")
        self.assertEqual(signing["serviceAccount"], p["signer"])
        self.assertNotEqual(signing["serviceAccount"], build["serviceAccount"])

    def test_equivalent_complete_and_collector_steps_install_the_same_dependency(self):
        plan = {"components": [{"id": "frontend", "buildArguments": {"SOURCE_REVISION": r.REVISION}}]}
        with patch.object(c.legacy, "accepted_catalog", return_value=accepted_policy(c.r)["accepted_release"]):
            build = c.build_request("frontend", REV, plan)
        self.assert_bootstrap(build["steps"][0])
        self.assertEqual(build["timeout"], "1800s")
        signing = c.signing_request(REV, "gs://" + r.policy()["project"] + "-attestation-source/complete-shop-v1/run/candidate.json#123", "sha256:" + "a" * 64)
        self.assert_bootstrap(signing["steps"][0], signing=True, transport=True)
        self.assertEqual(signing["timeout"], "1800s")
        support = collector.signing_request(REV)
        self.assert_bootstrap(support["steps"][0], signing=True)
        self.assertEqual(support["timeout"], "900s")
        for request in (signing, support):
            self.assertEqual(request["serviceAccount"], r.policy()["signer"])
            self.assertEqual(request["source"]["gitSource"]["revision"], REV)

    def test_sample_signer_bootstraps_before_python_and_preserves_positional_arguments(self):
        text = (ROOT / "cloudbuild/cloudbuild-attest.yaml").read_text(encoding="utf-8")
        self.assertIn("entrypoint: 'bash'", text)
        self.assertLess(text.index("apt-get install -y -qq python3"), text.index('exec python3 "$$@"'))
        self.assertIn("command -v gcloud >/dev/null", text)
        self.assertIn('exec python3 "$$@"\n      - \'--\'\n      - \'cloudbuild/scripts/attest-release.py\'', text)
        self.assertIn("'${_METADATA_FILE}'", text)
        self.assertIn("serviceAccount: 'projects/$PROJECT_ID/serviceAccounts/secure-delivery-attestation@$PROJECT_ID.iam.gserviceaccount.com'", text)


if __name__ == "__main__":
    unittest.main()
