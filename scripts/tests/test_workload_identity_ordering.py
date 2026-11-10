"""Verify the canonical Workload Identity binding's Terraform dependency graph.
Only an isolated offline fixture is initialized; no API request or apply is needed.
"""
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]

class WorkloadIdentityOrderingTest(unittest.TestCase):
    def test_binding_waits_for_pool_creating_cluster(self):
        cache = REPO / "terraform/bootstrap/.terraform/providers"
        if not shutil.which("terraform") or not cache.is_dir():
            self.skipTest("Terraform and installed pinned provider cache required")
        source = (REPO / "terraform/foundation/catalog-runtime.tf").read_text()
        binding = re.search(r'^resource "google_service_account_iam_member" "catalog_collector_identity" \{.*?^\}', source, re.S | re.M).group(0)
        with tempfile.TemporaryDirectory(dir=REPO / ".local-validation") as d:
            root = Path(d).resolve()
            self.assertTrue(root.is_relative_to((REPO / ".local-validation").resolve()))
            fixture = r'''terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}
variable "project_id" { default = "fixture-project" }
provider "google" {
  project = var.project_id
  access_token = "offline-fixture-not-a-credential"
  container_custom_endpoint = "http://127.0.0.1:9/"
  iam_custom_endpoint = "http://127.0.0.1:9/"
}
resource "google_container_cluster" "platform" {
  project = var.project_id
  name = "fixture-cluster"
  location = "us-central1-a"
  initial_node_count = 1
  workload_identity_config { workload_pool = "${var.project_id}.svc.id.goog" }
}
resource "google_service_account" "catalog_telemetry" {
  project = var.project_id
  account_id = "catalog-telemetry"
}
'''
            (root / "main.tf").write_text(fixture + binding, encoding="utf-8")
            shutil.copyfile(REPO / "terraform/bootstrap/.terraform.lock.hcl", root / ".terraform.lock.hcl")
            env = {k: v for k, v in os.environ.items() if not k.startswith(("TF_", "GOOGLE_", "CLOUDSDK_"))}
            env["TF_DATA_DIR"] = str(root / "tfdata")
            for args in [["init", "-backend=false", "-input=false", "-lockfile=readonly", "-plugin-dir=" + str(cache)], ["validate", "-no-color"], ["graph", "-type=plan"]]:
                r = subprocess.run(["terraform", "-chdir=" + str(root)] + args, env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=90)
                self.assertEqual(r.returncode, 0, r.stderr)
            self.assertRegex(r.stdout, r'"\[root\] google_service_account_iam_member.catalog_collector_identity \(expand\)" -> "\[root\] google_container_cluster.platform \(expand\)"')
            self.assertIn('role               = "roles/iam.workloadIdentityUser"', binding)
            self.assertIn('member             = "serviceAccount:${var.project_id}.svc.id.goog[dev/catalog-collector]"', binding)

if __name__ == "__main__": unittest.main()
