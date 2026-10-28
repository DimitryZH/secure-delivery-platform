"""Behavioral offline tests. Fakes never establish live Cloud Build acceptance."""
import base64
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("online_shop_release", ROOT / "cloudbuild/online-shop/release.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)
CONFIG = "c" * 40
BUILD_ID = "11111111-2222-3333-4444-555555555555"
DIGEST = "sha256:" + "a" * 64
IMAGE_CONFIG = "sha256:" + "b" * 64
P = {"project": "example-project", "region": "us-central1",
     "registry": "us-central1-docker.pkg.dev/example-project/secure-delivery",
     "producer": "projects/example-project/serviceAccounts/secure-delivery-build@example-project.iam.gserviceaccount.com",
     "signer": "projects/example-project/serviceAccounts/secure-delivery-attestation@example-project.iam.gserviceaccount.com"}
PLAN = {"sourceRevision": r.REVISION, "toolingRevision": r.REVISION,
        "components": [{"id": r.COMPONENT, "inputs": []}]}
REF = {"sha256": r.fingerprint(PLAN), "inputs_sha256": r.fingerprint([]),
       "planner_sha256": "sha256:" + "d" * 64, "contract_sha256": "sha256:" + "e" * 64,
       "uri": "git+" + r.AML + "@" + r.REVISION + "#" + r.WORKLOAD + "/build_plan.py"}


def successful_build():
    build = r.build_request(P, CONFIG, PLAN)
    build.update(name=r.build_url(P, BUILD_ID), id=BUILD_ID, projectId=P["project"],
                 status="SUCCESS", finishTime="2026-10-28T00:00:00Z",
                 sourceProvenance={"resolvedGitSource": build["source"]["gitSource"]},
                 results={"images": [{"name": build["images"][0], "digest": DIGEST}]})
    for step in build["steps"]:
        step.update(status="SUCCESS", exitCode=0, timing={"startTime": "service-output"})
    return build


class ReleaseTest(unittest.TestCase):
    def setUp(self):
        self.record = r.candidate(P, CONFIG, REF, BUILD_ID, DIGEST, IMAGE_CONFIG)
        self.cloud = Mock(token="offline-test-token")
        self.cloud.build.return_value = successful_build()
        self.cloud.image.return_value = IMAGE_CONFIG
        self.helper = Mock()
        self.helper.sign_and_create.return_value = {"name": "projects/example-project/occurrences/123"}
        self.helper.inspect_occurrence.return_value = "projects/example-project/occurrences/123"

    def sign(self):
        return r.sign(self.record, P, CONFIG, PLAN, REF, self.cloud, self.helper)

    def assert_no_signing(self):
        with self.assertRaises((ValueError, KeyError, TypeError, AttributeError)):
            self.sign()
        self.helper.sign_and_create.assert_not_called()
        self.helper.request_json.assert_not_called()

    def test_complete_candidate_verifies_then_signs_with_readback(self):
        result = self.sign()
        self.assertEqual(result["status"], "trusted")
        self.assertEqual(result["release_set_id"], self.record["release_set_id"])
        self.cloud.build.assert_called_once_with(P, BUILD_ID)
        self.cloud.image.assert_called_once_with(self.record["components"][0]["repository"], DIGEST)
        self.helper.request_json.assert_called_once()
        self.helper.validate_signature.assert_called_once()
        artifact = self.helper.sign_and_create.call_args.args[0]
        self.assertEqual(artifact, self.record["components"][0]["repository"] + "@" + DIGEST)

    def test_boolean_and_float_versions_with_original_identity_fail_before_evidence(self):
        for version in (True, 1.0):
            record = {**self.record, "version": version}
            payload = {key: value for key, value in record.items() if key != "release_set_id"}
            self.assertNotEqual(r.fingerprint(payload), record["release_set_id"])
            with self.subTest(version=repr(version)):
                with self.assertRaisesRegex(ValueError, "invalid_candidate_version"):
                    r.verify(record, P, CONFIG, PLAN, REF, self.cloud)
                with self.assertRaisesRegex(ValueError, "invalid_candidate_version"):
                    r.sign(record, P, CONFIG, PLAN, REF, self.cloud, self.helper)
        self.assertEqual(self.cloud.mock_calls, [])
        self.assertEqual(self.helper.mock_calls, [])

    def test_recomputed_identity_cannot_authorize_boolean_or_float_version(self):
        for version in (True, 1.0):
            payload = {key: value for key, value in self.record.items() if key != "release_set_id"}
            payload["version"] = version
            record = {**payload, "release_set_id": r.fingerprint(payload)}
            with self.subTest(version=repr(version)):
                with self.assertRaisesRegex(ValueError, "invalid_candidate_version"):
                    r.verify(record, P, CONFIG, PLAN, REF, self.cloud)
                with self.assertRaisesRegex(ValueError, "invalid_candidate_version"):
                    r.sign(record, P, CONFIG, PLAN, REF, self.cloud, self.helper)
        self.assertEqual(self.cloud.mock_calls, [])
        self.assertEqual(self.helper.mock_calls, [])

    def test_supplied_identity_is_checked_against_supplied_payload(self):
        record = copy.deepcopy(self.record)
        record["components"][0]["config_digest"] = "sha256:" + "f" * 64
        with self.assertRaisesRegex(ValueError, "candidate_identity_mismatch"):
            r.verify(record, P, CONFIG, PLAN, REF, self.cloud)
        with self.assertRaisesRegex(ValueError, "candidate_identity_mismatch"):
            r.sign(record, P, CONFIG, PLAN, REF, self.cloud, self.helper)
        self.assertEqual(self.cloud.mock_calls, [])
        self.assertEqual(self.helper.mock_calls, [])

    def test_integer_version_one_still_verifies(self):
        self.assertIs(type(self.record["version"]), int)
        result = r.verify(self.record, P, CONFIG, PLAN, REF, self.cloud)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["release_set_id"], self.record["release_set_id"])
        self.cloud.build.assert_called_once_with(P, BUILD_ID)
        self.cloud.image.assert_called_once()
        self.assertEqual(self.helper.mock_calls, [])

    def test_missing_duplicate_unexpected_membership_never_calls_authority(self):
        for components in ([], self.record["components"] * 2, [{"id": "frontend"}]):
            with self.subTest(components=components):
                self.record["components"] = components
                self.assert_no_signing()
        self.cloud.build.assert_not_called()

    def test_candidate_policy_mismatches_even_with_recomputed_identity_fail(self):
        original = copy.deepcopy(self.record)
        mutations = [lambda x: x.update(profile="catalog-v2"),
                     lambda x: x.update(profile_sha256="sha256:" + "0" * 64),
                     lambda x: x["source"].update(revision="1" * 40),
                     lambda x: x["source"].update(repository="https://evil.invalid/source"),
                     lambda x: x["configuration"].update(revision="1" * 40),
                     lambda x: x["plan"].update(inputs_sha256="sha256:" + "0" * 64),
                     lambda x: x["plan"].update(sha256="sha256:" + "0" * 64),
                     lambda x: x["build"].update(producer="unauthorized"),
                     lambda x: x["components"][0].update(platform="linux/arm64"),
                     lambda x: x["components"][0].update(repository="elsewhere.invalid/image"),
                     lambda x: x.update(environment="dev"),
                     lambda x: x.update(verification={"status": "passed"})]
        for mutation in mutations:
            self.record = copy.deepcopy(original)
            mutation(self.record)
            self.record.pop("release_set_id")
            self.record["release_set_id"] = r.fingerprint(self.record)
            with self.subTest(record=self.record):
                self.assert_no_signing()
        self.cloud.build.assert_not_called()

    def test_identity_deterministic_and_digest_changes_candidate(self):
        again = r.candidate(P, CONFIG, REF, BUILD_ID, DIGEST, IMAGE_CONFIG)
        self.assertEqual(again, self.record)
        changed = r.candidate(P, CONFIG, REF, BUILD_ID, "sha256:" + "f" * 64, IMAGE_CONFIG)
        self.assertNotEqual(changed["release_set_id"], self.record["release_set_id"])
        self.assertNotIn("environment", again)
        self.assertNotIn("verification", again)

    def test_authoritative_build_mismatches_prevent_signing(self):
        mutations = [lambda b: b.update(status="FAILURE"),
                     lambda b: b.pop("finishTime"),
                     lambda b: b.update(id="22222222-2222-3333-4444-555555555555"),
                     lambda b: b.update(projectId="other-project"),
                     lambda b: b.update(serviceAccount=P["signer"]),
                     lambda b: b["source"]["gitSource"].update(revision="1" * 40),
                     lambda b: b.update(sourceProvenance={}),
                     lambda b: b["steps"][0]["args"].append("echo fake"),
                     lambda b: b["steps"][1].update(allowFailure=True),
                     lambda b: b["steps"][0].update(status="FAILURE", exitCode=1),
                     lambda b: b["steps"].append({"name": "attacker"}),
                     lambda b: b.update(options={"logging": "CLOUD_LOGGING_ONLY", "env": ["BASH_ENV=evil"]}),
                     lambda b: b.update(substitutions={"_OTHER": "evil"}),
                     lambda b: b.update(dependencies=[{"gitSource": {"revision": "evil"}}]),
                     lambda b: b.update(availableSecrets={"secretManager": [{}]}),
                     lambda b: b["results"].update(images=[]),
                     lambda b: b["results"]["images"][0].update(digest="sha256:" + "f" * 64),
                     lambda b: b["results"]["images"][0].update(name="somewhere/image:tag")]
        for mutation in mutations:
            build = successful_build()
            mutation(build)
            self.cloud.build.return_value = build
            with self.subTest(build=build):
                self.assert_no_signing()

    def test_missing_build_evidence_stops_signing(self):
        for value in ({}, None, {"verification_status": "passed"}):
            self.cloud.build.return_value = value
            with self.subTest(value=value):
                self.assert_no_signing()
        self.cloud.build.side_effect = PermissionError("not authorized to read build")
        with self.assertRaises(PermissionError):
            self.sign()
        self.helper.sign_and_create.assert_not_called()

    def test_registry_mismatch_and_unavailability_stop_signing(self):
        self.cloud.image.return_value = "sha256:" + "0" * 64
        self.assert_no_signing()
        self.cloud.image.side_effect = ValueError("registry_platform_mismatch")
        self.assert_no_signing()

    def test_kms_create_readback_signature_failure_never_reports_trusted(self):
        for method in ("sign_and_create", "request_json", "inspect_occurrence", "validate_signature"):
            with self.subTest(method=method):
                self.helper = Mock()
                self.helper.sign_and_create.return_value = {"name": "projects/example-project/occurrences/123"}
                getattr(self.helper, method).side_effect = ValueError("denied")
                with self.assertRaises(ValueError):
                    self.sign()

    def test_actual_readback_subject_check_rejects_created_but_wrong_occurrence(self):
        helper = r.attestation_helper()
        observed = {"resourceUri": "elsewhere.invalid/wrong@" + DIGEST,
                    "name": "projects/example-project/occurrences/123"}
        with patch.object(helper, "sign_and_create", return_value={"name": observed["name"]}), \
                patch.object(helper, "request_json", return_value=observed), \
                patch.object(helper, "validate_signature") as signature:
            with self.assertRaisesRegex(ValueError, "matching_attestation_not_found"):
                r.sign(self.record, P, CONFIG, PLAN, REF, self.cloud, helper)
            signature.assert_not_called()

    def test_cli_build_and_signing_submission_targets_are_explicit_and_distinct(self):
        for action, expected_identity in (("submit", P["producer"]), ("submit-signing", P["signer"])):
            source = Mock()
            source.plan.return_value = PLAN
            self.cloud.request.return_value = json.dumps({"name": "projects/example-project/locations/us-central1/operations/test",
                                                          "metadata": {"build": {"id": BUILD_ID}}}).encode()
            arguments = ["release.py", action, "--configuration-revision", CONFIG]
            if action == "submit-signing":
                arguments += ["--candidate-object", "gs://example-project-attestation-source/catalog/candidate.json#123",
                              "--candidate-sha256", "sha256:" + "a" * 64]
            with self.subTest(action=action), patch.object(r, "reviewed_configuration", return_value=P), \
                    patch.object(r, "fetched") as fetched, patch.object(r, "plan_reference", return_value=REF), \
                    patch.object(r, "Cloud", return_value=self.cloud), patch.object(sys, "argv", arguments), \
                    patch("sys.stdout", new_callable=io.StringIO) as out:
                fetched.return_value.__enter__.return_value = source
                self.assertEqual(r.main(), 0)
                self.assertEqual(json.loads(out.getvalue())["build_id"], BUILD_ID)
                url, request = self.cloud.request.call_args.args
                self.assertEqual(url, "https://cloudbuild.googleapis.com/v1/projects/example-project/locations/us-central1/builds")
                self.assertEqual(request["serviceAccount"], expected_identity)
                self.assertEqual(request["source"]["gitSource"]["revision"], CONFIG)

    def test_machine_schema_and_profile_match_runtime_candidate_shape(self):
        schema = r.read(ROOT / "cloudbuild/online-shop/candidate-v1.schema.json")
        self.assertEqual(set(schema["properties"]), set(self.record))
        self.assertEqual(set(schema["required"]), set(self.record))
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(r.read(ROOT / "cloudbuild/online-shop/catalog-v1.json"), r.PROFILE)

    def test_cli_failure_outputs_no_partial_trust_or_raw_diagnostic(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(json.dumps(self.record))
            source = Mock()
            source.plan.return_value = PLAN
            with patch.object(r, "reviewed_configuration", return_value=P), \
                    patch.object(r, "fetched") as fetched, patch.object(r, "plan_reference", return_value=REF), \
                    patch.object(r, "Cloud", return_value=self.cloud), \
                    patch.object(r, "attestation_helper", return_value=self.helper), \
                    patch.object(sys, "argv", ["release.py", "attest", "--configuration-revision", CONFIG,
                                              "--candidate", str(path)]), patch("sys.stdout", new_callable=io.StringIO) as out:
                fetched.return_value.__enter__.return_value = source
                self.helper.request_json.side_effect = PermissionError("secret raw body")
                self.assertEqual(r.main(), 1)
                result = json.loads(out.getvalue())
                self.assertFalse(result["trusted"])
                self.assertNotIn("components", result)
                self.assertNotIn("secret", out.getvalue())

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(ValueError):
            r.decode('{"profile":"catalog-v1","profile":"anything"}')

    def test_supplied_profile_is_not_policy(self):
        with patch.object(r, "read", return_value={**r.PROFILE, "required_components": []}):
            with self.assertRaisesRegex(ValueError, "unapproved_profile"):
                r.policy()

    def test_signing_request_uses_separate_identity_and_data_only_transport(self):
        request = r.signing_request(P, CONFIG, "gs://example-project-attestation-source/catalog/candidate.json#123",
                                    "sha256:" + "a" * 64)
        self.assertEqual(request["serviceAccount"], P["signer"])
        self.assertNotEqual(request["serviceAccount"], P["producer"])
        self.assertEqual(request["source"]["gitSource"]["revision"], CONFIG)
        self.assertIn(" attest --configuration-revision ", request["steps"][0]["args"][1])
        self.assertNotIn("verification.json", json.dumps(request))
        for uri in ("gs://other-bucket/candidate.json#123", "gs://example-project-attestation-source/a.json",
                    "gs://example-project-attestation-source/a.json#123'; echo evil"):
            with self.assertRaises(ValueError):
                r.signing_request(P, CONFIG, uri, "sha256:" + "a" * 64)

    def test_feature_configuration_cannot_reach_cloud_submission(self):
        with patch.object(r, "reviewed_configuration", side_effect=ValueError("not_on_main")), \
                patch.object(r, "Cloud") as cloud, patch.object(sys, "argv", [
                    "release.py", "submit", "--configuration-revision", CONFIG]), \
                patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual(r.main(), 1)
            cloud.assert_not_called()


class AuthenticationLauncherTest(unittest.TestCase):
    def test_resolved_sdk_launcher_is_used_for_authentication(self):
        for launcher in (r"C:\sdk\bin\gcloud.cmd", "/usr/bin/gcloud"):
            def execute(args):
                # Model Windows CreateProcess: a bare name does not resolve the
                # SDK batch launcher, although PATH/PATHEXT resolution finds it.
                if args[0] != launcher:
                    raise FileNotFoundError("unresolved_sdk_launcher")
                return b"offline-test-token\n"

            with self.subTest(launcher=launcher), patch("shutil.which", return_value=launcher) as resolve, \
                    patch.object(r, "command", side_effect=execute) as command:
                cloud = r.Cloud()
                self.assertEqual(cloud.token, "offline-test-token")
                resolve.assert_called_once_with("gcloud")
                command.assert_called_once_with([launcher, "auth", "print-access-token", "--quiet"])

    def test_missing_sdk_launcher_stops_before_authentication(self):
        with patch("shutil.which", return_value=None), patch.object(r, "command") as command:
            with self.assertRaisesRegex(ValueError, "gcloud_executable_unavailable"):
                r.Cloud()
            command.assert_not_called()


class RegistryTest(unittest.TestCase):
    def test_registry_redirect_never_forwards_credentials(self):
        req = r.urllib.request.Request("https://us-central1-docker.pkg.dev/v2/p/r/i/blobs/sha256:a",
                                       headers={"Authorization": "Basic private", "Accept": "application/json"})
        target = r.SafeRedirect().redirect_request(req, None, 302, "Found", {},
                                                  "https://storage.googleapis.com/signed-object")
        self.assertIsNone(target.get_header("Authorization"))
        with self.assertRaises(ValueError):
            r.SafeRedirect().redirect_request(req, None, 302, "Found", {}, "https://attacker.invalid/blob")

    def exercise(self, config=None, mutate_manifest=None, wrong_blob=False):
        config = config or {"os": "linux", "architecture": "amd64", "config": {
            "Labels": {"org.opencontainers.image.revision": r.REVISION}}}
        raw_config = r.canonical(config)
        config_digest = "sha256:" + r.sha(raw_config)
        manifest = {"schemaVersion": 2, "config": {"digest": config_digest}, "layers": []}
        if mutate_manifest:
            mutate_manifest(manifest)
        raw = r.canonical(manifest)
        digest = "sha256:" + r.sha(raw)
        cloud = r.Cloud.__new__(r.Cloud)
        cloud.token = "not-live"
        with patch.object(cloud, "request", side_effect=[raw, b"tampered" if wrong_blob else raw_config]):
            return cloud.image(P["registry"] + "/online-shop-" + r.COMPONENT, digest), config_digest

    def test_manifest_and_config_content_addressing(self):
        actual, expected = self.exercise()
        self.assertEqual(actual, expected)
        with self.assertRaises(ValueError):
            self.exercise(wrong_blob=True)

    def test_actual_platform_revision_and_manifest_kind(self):
        for cfg in ({"os": "linux", "architecture": "arm64"},
                    {"os": "windows", "architecture": "amd64"},
                    {"os": "linux", "architecture": "amd64", "config": {"Labels": {}}}):
            with self.subTest(cfg=cfg), self.assertRaises(ValueError):
                self.exercise(config=cfg)
        with self.assertRaises(ValueError):
            self.exercise(mutate_manifest=lambda m: m.update(manifests=[]))

    def test_wrong_manifest_bytes_rejected_before_config_read(self):
        cloud = r.Cloud.__new__(r.Cloud)
        with patch.object(cloud, "request", return_value=b"tampered") as request:
            with self.assertRaisesRegex(ValueError, "registry_manifest_digest_mismatch"):
                cloud.image(P["registry"] + "/online-shop-" + r.COMPONENT, DIGEST)
            self.assertEqual(request.call_count, 1)


class MaterializationTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("SDP_AML_REPOSITORY"), "set SDP_AML_REPOSITORY for immutable local AML integration")
    def test_real_pinned_aml_plan_and_clean_bytes_without_checkout(self):
        source = r.Source(os.environ["SDP_AML_REPOSITORY"], r.REVISION)
        plan = source.plan()
        expected = r.fingerprint(plan)
        self.assertEqual(plan["components"][0]["buildArguments"]["SOURCE_REVISION"], r.REVISION)
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "context"
            r.materialize(source, expected, destination)
            self.assertEqual((destination / "products.json").read_bytes(),
                             source.blob(r.WORKLOAD + "/" + r.CONTEXT + "/products.json"))
            files = {row["path"]: row["sha256"] for row in plan["components"][0]["inputs"]}
            r.validate_context(destination, files)
            (destination / "untracked.txt").write_text("must not enter docker build")
            with self.assertRaisesRegex(ValueError, "undeclared_context_file"):
                r.validate_context(destination, files)
            with self.assertRaisesRegex(ValueError, "context_must_not_exist"):
                r.materialize(source, expected, destination)
            with self.assertRaisesRegex(ValueError, "plan_hash_mismatch"):
                r.materialize(source, "sha256:" + "0" * 64, Path(directory) / "wrong")

    def test_byte_drift_and_undeclared_files_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "products.json"
            file.write_bytes(b"original")
            files = {r.CONTEXT + "/products.json": r.sha(b"original")}
            r.validate_context(directory, files)
            file.write_bytes(b"modified")
            with self.assertRaisesRegex(ValueError, "context_bytes_mismatch"):
                r.validate_context(directory, files)
            file.write_bytes(b"original")
            (Path(directory) / "cache.pyc").write_bytes(b"untracked")
            with self.assertRaisesRegex(ValueError, "undeclared_context_file"):
                r.validate_context(directory, files)


class ReviewBoundaryTest(unittest.TestCase):
    def test_real_main_ancestry_and_execution_file_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "canonical.git"
            work = root / "work"
            r.command(["git", "init", "--bare", str(remote)])
            r.command(["git", "init", "-b", "main", str(work)])
            for key, value in (("user.name", "Offline Test"), ("user.email", "test@example.invalid"),
                               ("core.autocrlf", "false")):
                r.command(["git", "-C", str(work), "config", key, value])
            for path in r.TRUSTED_FILES:
                target = work / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes((ROOT / path).read_bytes().replace(b"\r\n", b"\n"))
            r.command(["git", "-C", str(work), "add", "--", *r.TRUSTED_FILES])
            r.command(["git", "-C", str(work), "commit", "-m", "test: create isolated reviewed fixture"])
            reviewed = r.command(["git", "-C", str(work), "rev-parse", "HEAD"]).decode().strip()
            r.command(["git", "-C", str(work), "push", str(remote), "main"])
            # All clones/commits are disposable test fixtures, never SDP/AML refs.
            with patch.object(r, "ROOT", work), patch.object(r, "HERE", work / "cloudbuild/online-shop"), \
                    patch.object(r, "SDP", str(root / "canonical")):
                self.assertEqual(r.reviewed_configuration(reviewed)["region"], "us-central1")
                (work / r.SCRIPT).write_text("# unreviewed modification\n")
                with self.assertRaisesRegex(ValueError, "unreviewed_execution_files"):
                    r.reviewed_configuration(reviewed)
                r.command(["git", "-C", str(work), "add", "--", r.SCRIPT])
                r.command(["git", "-C", str(work), "commit", "-m", "test: unmerged configuration"])
                feature = r.command(["git", "-C", str(work), "rev-parse", "HEAD"]).decode().strip()
                with self.assertRaises(subprocess.CalledProcessError):
                    r.reviewed_configuration(feature)


if __name__ == "__main__":
    unittest.main()
