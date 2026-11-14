import importlib.util
import tempfile
import os
import json
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "prepare-greenfield.py"
spec = importlib.util.spec_from_file_location("greenfield", SCRIPT)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

class GreenfieldRootsTests(unittest.TestCase):
    def setUp(self):
        (g.REPO / ".local-validation").mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(dir=g.REPO / ".local-validation")
        self.addCleanup(temporary.cleanup)
        isolated = patch.object(g, "ENV", Path(temporary.name))
        isolated.start(); self.addCleanup(isolated.stop)

    def test_no_legacy_inputs_or_kubernetes_in_cloud(self):
        files = g.expected()
        cloud = b"\n".join(v for k, v in files.items() if k.startswith("terraform/foundation/") and k.endswith(".tf"))
        self.assertNotIn(b'provider "kubernetes"', cloud)
        self.assertNotIn(b'resource "kubernetes_namespace"', cloud)
        self.assertNotIn(b'to = google_container_node_pool', cloud)
        self.assertIn(b'google_binary_authorization_policy.application', cloud)
        self.assertFalse(any(k.endswith((".tfvars", ".tfplan", ".tfstate")) or "/.terraform/" in k for k in files))
        self.assertNotIn("terraform/foundation/shop-endpoint.tf", files)
        self.assertNotIn("terraform/foundation/shop-observability.tf", files)
        self.assertEqual(files["terraform/foundation/gke-capacity.tf"], (g.REPO / "terraform/foundation/gke-capacity.tf").read_bytes())

    def test_optional_features_reuse_canonical_sources_and_same_state_owner(self):
        for endpoint, observability in ((False, False), (True, False), (True, True)):
            with self.subTest(endpoint=endpoint, observability=observability), tempfile.TemporaryDirectory(dir=g.REPO / '.local-validation') as d, patch.object(g, 'ENV', Path(d)):
                profile = {'version': 1, 'endpoint': endpoint, 'observability': observability}
                (Path(d) / 'foundation-features.private.json').write_text(json.dumps(profile))
                files = g.expected(); guard = files['terraform/foundation/greenfield-disabled.tf'].decode()
                for selected, name in ((endpoint, 'shop-endpoint.tf'), (observability, 'shop-observability.tf')):
                    path = 'terraform/foundation/' + name
                    self.assertEqual(path in files, selected)
                    if selected: self.assertEqual(files[path], (g.REPO / path).read_bytes())
                self.assertEqual('variable "shop_edge_enforce_evaluated_rules"' in guard, not endpoint)
                self.assertEqual('variable "shop_observability_enabled"' in guard, not observability)
                self.assertIn('greenfield_pool_creation', guard)
                self.assertEqual('monitoring/online-shop/frontend-errors.promql.tftpl' in files, observability)
                cloud = b'\n'.join(v for k,v in files.items() if k.startswith('terraform/foundation/') and k.endswith('.tf'))
                self.assertNotIn(b'provider "kubernetes"', cloud)
                for feature in ('endpoint', 'observability'):
                    key='terraform/foundation/'+feature+'-services_override.tf'
                    if profile[feature]: self.assertIn(b'setsubtract', files[key])
                g.materialize(); g.materialize(check=True)
                self.assertEqual(files['terraform/foundation/main.tf'], (g.REPO/'terraform/foundation/main.tf').read_bytes())

    def test_feature_selection_rejects_invalid_types_unknown_keys_and_stale_composition(self):
        with tempfile.TemporaryDirectory(dir=g.REPO / '.local-validation') as d, patch.object(g, 'ENV', Path(d)):
            path=Path(d)/'foundation-features.private.json'
            for value in ({'version':True,'endpoint':False,'observability':False},
                          {'version':1,'endpoint':1,'observability':False},
                          {'version':1,'endpoint':False,'observability':True},
                          {'version':1,'endpoint':True,'observability':True,'extra':1}):
                path.write_text(json.dumps(value))
                with self.assertRaises(SystemExit):g.expected()
            path.unlink();g.materialize()
            path.write_text(json.dumps({'version':1,'endpoint':True,'observability':True}))
            with self.assertRaises(SystemExit):g.materialize(check=True)
            g.materialize();g.materialize(check=True)
            # A downgrade cannot silently delete generated resources/files.
            path.unlink()
            with self.assertRaises(SystemExit):g.materialize()

    def test_freshness_and_unexpected_files_fail_closed(self):
        with tempfile.TemporaryDirectory(dir=g.REPO / ".local-validation") as d, patch.object(g, "ENV", Path(d)):
            g.materialize()
            g.materialize(check=True)
            root = Path(d) / "roots"
            for source in ["terraform/bootstrap/main.tf", "terraform/foundation/gke-capacity.tf"]:
                f = root / source
                f.write_text("stale")
                with self.assertRaises(SystemExit): g.materialize(check=True)
                g.materialize()
            (root / "terraform/foundation/terraform.tfvars").write_text("unexpected")
            with self.assertRaises(SystemExit): g.materialize()

    def test_state_path_and_quota_envelope(self):
        files = g.expected()
        backend = files["terraform/bootstrap/backend.tf"].decode()
        self.assertIn((g.ENV.resolve() / "state/bootstrap/terraform.tfstate").as_posix(), backend)
        override = files["terraform/foundation/greenfield_override.tf"].decode()
        self.assertIn("default = true", override.replace("  ", " "))
        guard = files["terraform/foundation/greenfield-disabled.tf"].decode()
        self.assertIn("precondition", guard)
        self.assertIn("var.gke_create_separate_default_pool", guard)
        self.assertEqual(1 * 2 + 1 * 4, 6)
        self.assertEqual(2 * 2 + 2 * 4, 12)
        for name in ["gke.tf", "complete-shop.tf"]:
            text = files["terraform/foundation/" + name].decode()
            self.assertIn("max_surge", text)
            self.assertIn("max_unavailable", text)
            self.assertNotIn("autoscaling {", text)

    def test_execution_guard_rejects_overrides_and_wrong_backend(self):
        with tempfile.TemporaryDirectory(dir=g.REPO / ".local-validation") as d, patch.object(g, "ENV", Path(d)), patch.object(Path, "home", return_value=Path(d) / "home"):
            home = Path(d) / "home"
            adc_dir = home / "isolated-sdk"
            adc_dir.mkdir(parents=True)
            (adc_dir / "application_default_credentials.json").write_text("not-read")
            (Path(d) / "foundation.tfvars").write_text('deployment_operator_principal = "user:operator@example.test"\n')
            settings = Path(d) / "execution-settings.private.json"
            settings.write_text(json.dumps({"version": 1, "sdk_config_directory": str(adc_dir)}), encoding="utf-8")
            g.materialize()
            e = {"TF_DATA_DIR": str(Path(d) / "tfdata/foundation"), "TF_WORKSPACE": "default",
                 "GOOGLE_APPLICATION_CREDENTIALS": str(adc_dir / "application_default_credentials.json"),
                 "CLOUDSDK_CONFIG": str(adc_dir), "CLOUDSDK_CORE_ACCOUNT": "operator@example.test", "CLOUDSDK_CORE_PROJECT": "sdp-gcp"}
            g.check_execution("foundation", e)
            settings.write_text(json.dumps({"version": 1, "sdk_config_directory": "relative-sdk"}), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "absolute isolated SDK"):
                g.check_execution("foundation", e)
            settings.write_text(json.dumps({"version": 1, "sdk_config_directory": str(adc_dir)}), encoding="utf-8")
            for key, value in [("TF_CLI_ARGS", "-var-file=other.tfvars"), ("TF_VAR_project_id", "other"), ("GOOGLE_CREDENTIALS", "other"), ("TF_DATA_DIR", "other"), ("CLOUDSDK_CORE_ACCOUNT", "other@example.test")]:
                with self.subTest(key=key), self.assertRaises(SystemExit):
                    g.check_execution("foundation", dict(e, **{key: value}))
            data = Path(e["TF_DATA_DIR"])
            data.mkdir(parents=True)
            metadata = data / "terraform.tfstate"
            for config in [{"bucket": "other", "prefix": "secure-delivery-platform/foundation"},
                           {"bucket": "sdp-gcp-738317279206-tf-state", "prefix": "other"},
                           {"bucket": "sdp-gcp-738317279206-tf-state", "prefix": "secure-delivery-platform/foundation", "access_token": "fake"}]:
                metadata.write_text(json.dumps({"backend": {"type": "gcs", "config": config}}))
                with self.assertRaises(SystemExit): g.check_execution("foundation", e)
            metadata.write_text(json.dumps({"backend": {"type": "gcs", "config": {"bucket": "sdp-gcp-738317279206-tf-state", "prefix": "secure-delivery-platform/foundation"}}}))
            g.check_execution("foundation", e)

    def test_state_path_is_independent_of_cwd(self):
        before = g.expected()["terraform/bootstrap/backend.tf"]
        with tempfile.TemporaryDirectory(dir=g.REPO / ".local-validation") as d:
            previous = Path.cwd()
            try:
                os.chdir(d)
                self.assertEqual(g.expected()["terraform/bootstrap/backend.tf"], before)
            finally:
                os.chdir(previous)

if __name__ == "__main__": unittest.main()
