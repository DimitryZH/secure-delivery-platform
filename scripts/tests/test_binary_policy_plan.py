"""Offline regression using the pinned provider and a loopback-only policy API.
No Google credentials, cloud calls, apply, or state import are used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import unittest

REPO = Path(__file__).resolve().parents[2]

class PolicyPlanTest(unittest.TestCase):
    def test_imported_policy_requires_known_attestor_before_creation(self):
        cache = REPO / "terraform/bootstrap/.terraform/providers"
        if not shutil.which("terraform") or not cache.is_dir():
            self.skipTest("Terraform and installed locked provider cache required")
        class Handler(BaseHTTPRequestHandler):
            calls = []
            def do_GET(self):
                self.calls.append(self.path)
                if self.path.split("?", 1)[0] != "/projects/fixture-project/policy":
                    self.send_response(404); self.end_headers(); return
                raw = json.dumps({"name": "projects/fixture-project/policy", "globalPolicyEvaluationMode": "ENABLE", "defaultAdmissionRule": {"evaluationMode": "ALWAYS_ALLOW", "enforcementMode": "ENFORCED_BLOCK_AND_AUDIT_LOG"}}).encode()
                self.send_response(200); self.send_header("Content-Type", "application/json"); self.end_headers(); self.wfile.write(raw)
            def log_message(self, *args): pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            with tempfile.TemporaryDirectory(dir=REPO / ".local-validation") as d:
                root = Path(d).resolve()
                self.assertTrue(root.is_relative_to((REPO / ".local-validation").resolve()))
                (root / "policy.tf").write_bytes((REPO / "terraform/foundation/binary-authorization.tf").read_bytes())
                fixture = r'''terraform {
  required_providers {
    google = { source = "hashicorp/google", version = "~> 5.0" }
  }
}
variable "project_id" { default = "fixture-project" }
variable "gke_location" { default = "us-central1-a" }
variable "gke_cluster_name" { default = "fixture-cluster" }
provider "google" {
  project = var.project_id
  access_token = "offline-fixture-not-a-credential"
  binary_authorization_custom_endpoint = "ENDPOINT"
}
resource "google_binary_authorization_attestor" "verification" {
  project = var.project_id
  name = "fixture-attestor"
  attestation_authority_note { note_reference = "projects/fixture-project/notes/fixture-note" }
}
'''
                (root / "fixture.tf").write_text(fixture.replace("ENDPOINT", f"http://127.0.0.1:{server.server_port}/"), encoding="utf-8")
                shutil.copyfile(REPO / "terraform/bootstrap/.terraform.lock.hcl", root / ".terraform.lock.hcl")
                env = {k: v for k, v in os.environ.items() if not k.startswith(("TF_", "GOOGLE_", "CLOUDSDK_"))}
                env["TF_DATA_DIR"] = str(root / "tfdata")
                for args in [["init", "-backend=false", "-input=false", "-lockfile=readonly", "-plugin-dir=" + str(cache)], ["plan", "-input=false", "-out=" + str(root / "test.tfplan")], ["show", "-json", str(root / "test.tfplan")]]:
                    r = subprocess.run(["terraform", "-chdir=" + str(root)] + args, env=env, capture_output=True, encoding="utf-8", errors="replace", timeout=90)
                    self.assertEqual(r.returncode, 0, r.stderr)
                plan = json.loads(r.stdout)
                policy = next(x for x in plan["resource_changes"] if x["address"] == "google_binary_authorization_policy.application")
                rule = policy["change"]["after"]["cluster_admission_rules"][0]
                self.assertEqual(rule["require_attestations_by"], ["projects/fixture-project/attestors/fixture-attestor"])
                self.assertEqual(rule["evaluation_mode"], "REQUIRE_ATTESTATION")
                self.assertEqual(rule["enforcement_mode"], "ENFORCED_BLOCK_AND_AUDIT_LOG")
                self.assertEqual(policy["change"]["importing"]["id"], "projects/fixture-project")
                attestor = next(x for x in plan["resource_changes"] if x["address"] == "google_binary_authorization_attestor.verification")
                self.assertTrue(attestor["change"]["after_unknown"]["id"])
                config = next(x for x in plan["configuration"]["root_module"]["resources"] if x["address"] == policy["address"])
                self.assertIn("google_binary_authorization_attestor.verification", config["depends_on"])
                self.assertTrue(Handler.calls)
        finally:
            server.shutdown(); server.server_close()

if __name__ == "__main__": unittest.main()
