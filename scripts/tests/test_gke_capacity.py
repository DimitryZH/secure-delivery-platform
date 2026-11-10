"""Plan canonical pool sizing with the locked provider, offline and without apply."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]


class GkeCapacityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cache = Path(os.environ.get("SDP_TERRAFORM_PROVIDER_DIR",
                                    str(REPO / "terraform/bootstrap/.terraform/providers"))).resolve()
        if not shutil.which("terraform") or not cache.is_dir():
            raise unittest.SkipTest("Terraform and installed locked provider cache required")
        (REPO / ".local-validation").mkdir(parents=True, exist_ok=True)
        cls.temporary = tempfile.TemporaryDirectory(dir=REPO / ".local-validation")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.root = Path(cls.temporary.name).resolve()
        cls.env = {k: v for k, v in os.environ.items() if not k.startswith(("TF_", "GOOGLE_", "CLOUDSDK_"))}
        cls.env["TF_DATA_DIR"] = str(cls.root / "tfdata")
        source = REPO / "terraform/foundation"
        for name in ["variables.tf", "gke.tf", "gke-capacity.tf"]:
            shutil.copyfile(source / name, cls.root / name)
        shop = re.search(r'^resource "google_container_node_pool" "complete_shop" \{.*?^\}',
                         (source / "complete-shop.tf").read_text(), re.M | re.S).group(0)
        (cls.root / "shop.tf").write_text(shop, encoding="utf-8")
        shutil.copyfile(REPO / "terraform/bootstrap/.terraform.lock.hcl", cls.root / ".terraform.lock.hcl")
        (cls.root / "fixture.tf").write_text('''terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "= 5.45.2" }
  }
}
provider "google" {
  project = var.project_id
  access_token = "offline-fixture-not-a-credential"
  container_custom_endpoint = "http://127.0.0.1:9/"
  iam_custom_endpoint = "http://127.0.0.1:9/"
  binary_authorization_custom_endpoint = "http://127.0.0.1:9/"
}
resource "google_service_account" "node" { account_id = "fixture-node" }
resource "google_project_service" "required" {
  for_each = toset([])
  service = each.value
}
resource "google_binary_authorization_policy" "application" {
  default_admission_rule {
    evaluation_mode = "ALWAYS_ALLOW"
    enforcement_mode = "ENFORCED_BLOCK_AND_AUDIT_LOG"
  }
}
''', encoding="utf-8")
        result = cls.run_tf("init", "-backend=false", "-input=false", "-lockfile=readonly", "-plugin-dir=" + str(cache))
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)

    @classmethod
    def run_tf(cls, *args):
        return subprocess.run(["terraform", "-chdir=" + str(cls.root), *args], env=cls.env,
                              capture_output=True, encoding="utf-8", errors="replace", timeout=90)

    def plan(self, mode=None, separate=True, valid=True):
        values = {"project_id": "fixture-project", "deployment_operator_principal": "user:operator@example.test",
                  "gke_create_separate_default_pool": separate}
        if mode is not None:
            values["gke_capacity_mode"] = mode
        inputs = self.root / "inputs.tfvars.json"
        inputs.write_text(json.dumps(values), encoding="utf-8")
        result = self.run_tf("plan", "-refresh=false", "-input=false", "-no-color",
                             "-var-file=" + str(inputs), "-out=" + str(self.root / "fixture.tfplan"))
        if not valid:
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("gke_capacity_mode", result.stdout + result.stderr)
            return
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.run_tf("show", "-json", str(self.root / "fixture.tfplan"))
        self.assertEqual(result.returncode, 0, result.stderr)
        plan = json.loads(result.stdout)
        return {x["address"]: x["change"] for x in plan["resource_changes"]}

    def test_running(self):
        changes = self.plan("running")
        for pool in ["existing_default", "complete_shop"]:
            after = changes["google_container_node_pool." + pool]["after"]
            self.assertEqual(after["node_count"], 1)
            self.assertEqual(after["upgrade_settings"][0]["max_surge"], 1)
            self.assertEqual(after["upgrade_settings"][0]["max_unavailable"], 0)
            self.assertEqual(after["node_config"][0]["workload_metadata_config"][0]["mode"], "GKE_METADATA")

    def test_paused_changes_only_managed_pool_counts(self):
        running, paused = self.plan("running"), self.plan("paused")
        self.assertEqual(running.keys(), paused.keys())
        for address in running:
            before, after = running[address]["after"], paused[address]["after"]
            if address.startswith("google_container_node_pool."):
                self.assertEqual(before["node_count"], 1)
                self.assertEqual(after["node_count"], 0)
                before = dict(before, node_count=0)
            self.assertEqual(before, after, address)
        self.assertEqual(paused["google_container_cluster.platform"]["after"]["initial_node_count"], 1)

    def test_invalid_modes(self):
        for value in ["stop", "", "PAUSED"]:
            with self.subTest(value=value):
                self.plan(value, valid=False)

    def test_separate_pools_require_explicit_mode(self):
        self.plan(valid=False)

    def test_historical_default_pool_stays_unmanaged_for_count(self):
        for mode in [None, "running"]:
            with self.subTest(mode=mode):
                changes = self.plan(mode, separate=False)
                default = changes["google_container_node_pool.existing_default"]
                self.assertIsNone(default["after"].get("node_count"))
                self.assertTrue(default["after_unknown"]["node_count"])
                self.assertEqual(changes["google_container_node_pool.complete_shop"]["after"]["node_count"], 1)
                self.assertFalse(changes["google_container_cluster.platform"]["after"]["remove_default_node_pool"])

    def test_historical_pause_is_rejected(self):
        self.plan("paused", separate=False, valid=False)


if __name__ == "__main__":
    unittest.main()
