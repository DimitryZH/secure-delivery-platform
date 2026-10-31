"""Offline security regressions; API/tool fakes are never publisher evidence."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import urllib.error
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("collector_adoption", ROOT / "cloudbuild/online-shop/collector.py")
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)
REV = "a" * 40


def digest(raw):
    return "sha256:" + c.r.sha(raw)


def http(code):
    return urllib.error.HTTPError("https://registry.invalid/redacted", code, "test", {}, None)


class Registry:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def get(self, kind, identity):
        self.calls.append((kind, identity))
        value = self.data[(kind, identity)]
        if isinstance(value, Exception):
            raise value
        return value


class CollectorTests(unittest.TestCase):
    def setUp(self):
        self.policy = copy.deepcopy(c.policy())
        self.config = {"os": "linux", "architecture": "amd64"}
        self.layer = b"compressed-layer-fixture"
        self.make_image()
        self.reader = Registry(self.data)
        self.blobs = patch.object(c, "blob_bytes", side_effect=lambda cloud, repository, identity: self.reader.get("blobs", identity))
        self.blobs.start()
        self.addCleanup(self.blobs.stop)
        self.cloud = Mock(token="private-token")
        self.occurrences = {}
        self.pages = None
        self.cloud.request.side_effect = self.api
        self.helper = Mock()
        self.helper.inspect_occurrence.side_effect = c.r.attestation_helper().inspect_occurrence
        self.helper.sign_and_create.side_effect = self.create
        self.signer = patch.object(c, "signer_identity")
        self.signer.start()
        self.addCleanup(self.signer.stop)

    def make_image(self):
        config = c.r.canonical(self.config)
        self.policy["config_digest"] = digest(config)
        self.manifest = {"schemaVersion": 2, "config": {"digest": digest(config), "size": len(config)},
                         "layers": [{"digest": digest(self.layer), "size": len(self.layer)}]}
        self.encode_manifest(config)

    def encode_manifest(self, config=None):
        config = c.r.canonical(self.config) if config is None else config
        raw = c.r.canonical(self.manifest)
        self.policy["manifest_digest"] = digest(raw)
        self.policy["mirror_image"] = c.r.policy()["registry"] + "/otelcol-contrib@" + digest(raw)
        self.index = {"schemaVersion": 2, "manifests": [{"digest": digest(raw), "size": len(raw),
                                                       "platform": {"os": "linux", "architecture": "amd64"}}]}
        self.data = {("manifests", digest(raw)): raw, ("blobs", self.policy["config_digest"]): config,
                     ("blobs", digest(self.layer)): self.layer}
        self.encode_index()

    def encode_index(self):
        raw = c.r.canonical(self.index)
        self.policy["index_digest"] = digest(raw)
        self.data[("manifests", digest(raw))] = raw

    def api(self, url, body=None, registry=False):
        if registry:
            kind, identity = url.rsplit("/", 2)[-2:]
            return self.reader.get(kind, identity)
        if "/occurrences?" in url:
            return c.r.canonical(self.pages.pop(0) if self.pages is not None else {"occurrences": list(self.occurrences.values())})
        if "/occurrences/" in url:
            return c.r.canonical(self.occurrences[url.split("/v1/")[1]])
        raise AssertionError("Unexpected API call")

    def occurrence(self):
        attestor, note, key, public = c.authority()
        reference, identity = self.policy["mirror_image"].split("@")
        payload = {"critical": {"identity": {"docker-reference": reference}, "image": {"docker-manifest-digest": identity},
                                "type": "Google Cloud BinAuthz container signature"}}
        return {"name": "projects/" + c.r.policy()["project"] + "/occurrences/fixture-1", "resourceUri": self.policy["mirror_image"],
                "noteName": note, "attestation": {"serializedPayload": c.base64.b64encode(c.r.canonical(payload)).decode(),
                "signatures": [{"publicKeyId": public, "signature": "offline-signature"}]}}

    def create(self, *args):
        value = self.occurrence()
        self.occurrences[value["name"]] = value
        return value

    def publisher(self):
        with patch.object(c, "cosign"), patch.object(c, "Upstream", return_value=self.reader):
            return c.publisher(self.policy)

    def signing(self, **kwargs):
        with patch.object(c, "publisher", return_value={"status": "publisher_verified"}):
            return c.attest(self.policy, self.cloud, self.helper, **kwargs)

    def test_live_policy_is_exact_and_application_acceptance_is_unchanged(self):
        policy = c.policy()
        self.assertEqual(policy["manifest_digest"], "sha256:ac0bb9cdc844b55d2fd2655d03e596243787d6a8c52dd408b1dc96dd1bd372ee")
        accepted = c.r.read(ROOT / "deploy/online-shop/policy.json")["accepted_release"]
        self.assertEqual(accepted["release_set_id"], "sha256:b9750798a71f543d0f75d0f48b1086f7c33427804eb07a795dd289faddaa3160")

    def test_policy_rejects_alternate_repository_mirror_publisher_and_version_types(self):
        original = c.r.read
        for field, value in (("mirror_image", "unapproved/image@" + "a"*64), ("upstream_repository", "ghcr.io/attacker/image"),
                             ("certificate_identity", "https://attacker.invalid"), ("certificate_oidc_issuer", "https://other.invalid")):
            document = original(ROOT / "deploy/online-shop/policy.json")
            document["collector"][field] = value
            with self.subTest(field=field), patch.object(c.r, "read", side_effect=lambda path: document if Path(path).name == "policy.json" else original(path)):
                with self.assertRaises(ValueError): c.policy()
        for version in (True, 1.0):
            document = original(ROOT / "deploy/online-shop/policy.json"); document["version"] = version
            with patch.object(c.r,"read",return_value=document), self.assertRaisesRegex(ValueError,"policy_version"): c.policy()

    def test_cosign_uses_exact_identity_issuer_index_without_ambient_trust_overrides(self):
        output = [{"critical": {"image": {"docker-manifest-digest": self.policy["index_digest"]}}}]
        with patch.object(c,"tool",return_value="pinned-cosign"), patch.object(c,"run",return_value=c.r.canonical(output)) as run, patch.dict(os.environ,{"COSIGN_TRUSTED_ROOT":"untrusted","SIGSTORE_ROOT_FILE":"untrusted"}):
            c.cosign(self.policy)
        args = run.call_args.args[0]
        self.assertIn("--certificate-identity=" + self.policy["certificate_identity"],args)
        self.assertIn("--certificate-oidc-issuer=" + self.policy["certificate_oidc_issuer"],args)
        self.assertEqual(args[-1],self.policy["upstream_repository"] + "@" + self.policy["index_digest"])
        self.assertNotIn("COSIGN_TRUSTED_ROOT",run.call_args.kwargs["env"])
        self.assertNotIn("SIGSTORE_ROOT_FILE",run.call_args.kwargs["env"])
        self.assertFalse(any("ignore" in x or "insecure" in x for x in args))

    def test_empty_or_wrong_cosign_claim_cannot_authorize_index(self):
        for result in ([], [{"critical":{"image":{"docker-manifest-digest":"sha256:"+"0"*64}}}]):
            with patch.object(c,"tool",return_value="pinned-cosign"), patch.object(c,"run",return_value=c.r.canonical(result)), self.assertRaisesRegex(ValueError,"publisher_signature"):
                c.cosign(self.policy)

    def test_publisher_failure_precedes_registry_reads(self):
        with patch.object(c,"cosign",side_effect=ValueError("bad_signature")), patch.object(c,"Upstream") as upstream:
            with self.assertRaisesRegex(ValueError,"bad_signature"): c.publisher(self.policy)
        upstream.assert_not_called()

    def test_correct_signed_index_manifest_config_and_layer_pass(self):
        proof = self.publisher()
        self.assertEqual(proof["status"],"publisher_verified")
        self.assertTrue(proof["layer_bytes_verified"])

    def test_index_hash_and_unique_platform_membership_are_required(self):
        self.data[("manifests",self.policy["index_digest"])]=b"wrong bytes"
        with self.assertRaisesRegex(ValueError,"index_hash"): self.publisher()
        for mutation in (lambda: self.index["manifests"].append(copy.deepcopy(self.index["manifests"][0])),
                         lambda: self.index["manifests"][0]["platform"].update(architecture="arm64"),
                         lambda: self.index["manifests"][0].update(digest="sha256:"+"0"*64)):
            self.make_image(); mutation(); self.encode_index(); self.reader.data=self.data
            with self.assertRaisesRegex(ValueError,"platform_membership"): self.publisher()

    def test_manifest_bytes_and_member_size_are_required(self):
        self.data[("manifests",self.policy["manifest_digest"])]=b"wrong bytes"
        with self.assertRaisesRegex(ValueError,"manifest_hash"): self.publisher()
        self.make_image(); self.index["manifests"][0]["size"]+=1; self.encode_index(); self.reader.data=self.data
        with self.assertRaisesRegex(ValueError,"member_size"): self.publisher()

    def test_recomputed_wrong_platform_still_fails(self):
        self.config["architecture"]="arm64"; self.make_image(); self.reader.data=self.data
        with self.assertRaisesRegex(ValueError,"collector_platform"): self.publisher()

    def test_config_binding_and_actual_bytes_are_verified(self):
        self.data[("blobs",self.policy["config_digest"])]=b"changed config"
        with self.assertRaisesRegex(ValueError,"config_hash"): self.publisher()
        self.make_image(); self.manifest["config"]["digest"]="sha256:"+"0"*64; self.encode_manifest(); self.reader.data=self.data
        with self.assertRaisesRegex(ValueError,"config_binding"): self.publisher()

    def test_layer_content_size_and_external_urls_fail_closed(self):
        self.data[("blobs",digest(self.layer))]=b"corrupt"
        with self.assertRaisesRegex(ValueError,"layer_hash"): self.publisher()
        self.make_image(); self.manifest["layers"][0]["size"]+=1; self.encode_manifest(); self.reader.data=self.data
        with self.assertRaisesRegex(ValueError,"layer_hash"): self.publisher()
        self.make_image(); self.manifest["layers"][0]["urls"]=["https://external.invalid/layer"]; self.encode_manifest(); self.reader.data=self.data
        with self.assertRaisesRegex(ValueError,"descriptor"): self.publisher()

    def test_mirror_corruption_prevents_signing(self):
        for identity in (self.policy["manifest_digest"],self.policy["config_digest"],digest(self.layer)):
            data=copy.deepcopy(self.data)
            self.data[("manifests" if identity==self.policy["manifest_digest"] else "blobs",identity)]=b"corrupt"
            with self.assertRaises(ValueError): self.signing()
            self.helper.sign_and_create.assert_not_called()
            self.data.clear(); self.data.update(data)

    def test_mirror_reuses_existing_complete_image_and_checks_publisher_again(self):
        with patch.object(c,"publisher",return_value={}) as publisher, patch.object(c,"copy") as copier:
            self.assertEqual(c.mirror(self.policy,self.cloud)["status"],"mirror_already_present")
        publisher.assert_called_once(); copier.assert_not_called()

    def test_existing_partial_image_or_registry_denial_never_triggers_copy(self):
        for key,value in ((("blobs",self.policy["config_digest"]),http(404)),(("manifests",self.policy["manifest_digest"]),http(403))):
            data=self.data[key]; self.data[key]=value
            with patch.object(c,"publisher",return_value={}),patch.object(c,"copy") as copier,self.assertRaises(urllib.error.HTTPError): c.mirror(self.policy,self.cloud)
            copier.assert_not_called();self.data[key]=data

    def test_missing_manifest_copies_once_then_validates_actual_destination(self):
        key=("manifests",self.policy["manifest_digest"]); raw=self.data[key]; self.data[key]=http(404)
        def copy_image(*args): self.data[key]=raw
        with patch.object(c,"publisher",return_value={}),patch.object(c,"copy",side_effect=copy_image) as copier:
            self.assertEqual(c.mirror(self.policy,self.cloud)["status"],"mirrored")
        copier.assert_called_once()

    def test_uncertain_copy_recovers_by_readback_without_retry(self):
        key=("manifests",self.policy["manifest_digest"]);raw=self.data[key];self.data[key]=http(404)
        def uncertain(*args):self.data[key]=raw;raise TimeoutError()
        with patch.object(c,"publisher",return_value={}),patch.object(c,"copy",side_effect=uncertain) as copier:
            self.assertEqual(c.mirror(self.policy,self.cloud)["status"],"mirror_recovered")
        copier.assert_called_once()

    def test_crane_copy_is_digest_only_and_token_is_stdin_only(self):
        with patch.object(c,"tool",return_value="pinned-crane"),patch.object(c,"run",return_value=b"") as run:
            c.copy(self.policy,self.cloud)
        login,copy_call=run.call_args_list
        self.assertEqual(login.kwargs["input"],b"private-token\n")
        self.assertNotIn("private-token",str(login.args))
        self.assertEqual(copy_call.args[0],["pinned-crane","copy","--jobs=1",self.policy["upstream_repository"]+"@"+self.policy["manifest_digest"],self.policy["mirror_image"]])
        self.assertFalse(Path(login.kwargs["env"]["DOCKER_CONFIG"]).exists())

    def test_signer_identity_failure_precedes_verification_and_kms(self):
        with patch.object(c,"signer_identity",side_effect=ValueError("wrong_identity")),patch.object(c,"verify") as verifier,self.assertRaisesRegex(ValueError,"wrong_identity"):
            c.attest(self.policy,self.cloud,self.helper)
        verifier.assert_not_called();self.helper.sign_and_create.assert_not_called();self.cloud.request.assert_not_called()

    def test_publisher_failure_prevents_kms_even_with_existing_occurrence(self):
        self.create()
        with patch.object(c,"publisher",side_effect=ValueError("publisher_failed")),self.assertRaisesRegex(ValueError,"publisher_failed"):
            c.attest(self.policy,self.cloud,self.helper)
        self.cloud.request.assert_not_called();self.helper.sign_and_create.assert_not_called()

    def test_new_attestation_has_fresh_verification_and_actual_signature_readback(self):
        result=self.signing()
        self.assertEqual(result["status"],"trusted");self.assertEqual(result["kind"],"supporting_image")
        self.assertNotIn("release_set_id",result)
        self.helper.sign_and_create.assert_called_once()
        self.helper.validate_signature.assert_called_once()
        self.assertEqual(result["occurrence"],self.occurrence()["name"])

    def test_repeated_signing_and_inspection_reuse_valid_occurrence(self):
        first=self.signing();second=self.signing();third=self.signing(inspect=True)
        self.assertEqual(first["occurrence"],second["occurrence"])
        self.assertEqual(second["attestation_action"],"reused");self.assertEqual(third["attestation_action"],"reused")
        self.helper.sign_and_create.assert_called_once()
        self.assertEqual(self.helper.validate_signature.call_count,3)

    def test_inspect_never_creates_missing_attestation(self):
        with self.assertRaisesRegex(ValueError,"attestation_missing"):self.signing(inspect=True)
        self.helper.sign_and_create.assert_not_called()

    def test_invalid_existing_signature_is_not_replaced_with_new_occurrence(self):
        self.create();self.helper.validate_signature.side_effect=ValueError("signature_not_verified")
        with self.assertRaisesRegex(ValueError,"signature_not_verified"):self.signing()
        self.helper.sign_and_create.assert_not_called()

    def test_uncertain_creation_recovers_existing_result_and_does_not_resign(self):
        def uncertain(*args):self.create();raise TimeoutError()
        self.helper.sign_and_create.side_effect=uncertain
        self.assertEqual(self.signing()["attestation_action"],"recovered")
        self.assertEqual(self.signing()["attestation_action"],"reused")
        self.helper.sign_and_create.assert_called_once()

    def test_uncertain_creation_without_proof_does_not_claim_trusted_or_retry(self):
        self.helper.sign_and_create.side_effect=TimeoutError()
        with self.assertRaisesRegex(ValueError,"uncertain_inspect_before_retry"):self.signing()
        self.helper.sign_and_create.assert_called_once()

    def test_post_create_note_subject_payload_key_and_signature_must_match(self):
        for mutation in (lambda x:x.update(noteName="projects/other/notes/other"),lambda x:x.update(resourceUri="other@sha256:"+"0"*64),
                         lambda x:x["attestation"]["signatures"][0].update(publicKeyId="other"),
                         lambda x:x["attestation"].update(serializedPayload=c.base64.b64encode(b'{}').decode())):
            self.occurrences.clear()
            def bad(*args):value=self.create();mutation(value);return value
            self.helper.sign_and_create.side_effect=bad
            with self.assertRaises(ValueError):self.signing()
        self.occurrences.clear();self.helper.sign_and_create.side_effect=self.create
        self.helper.validate_signature.side_effect=ValueError("signature_not_verified")
        with self.assertRaisesRegex(ValueError,"signature_not_verified"):self.signing()

    def test_paginated_occurrences_are_read_and_cycles_fail_closed(self):
        value=self.create();self.pages=[{"nextPageToken":"second"},{"occurrences":[value]}]
        self.assertEqual(c.existing(self.policy,self.cloud,self.helper),[value["name"]])
        self.pages=[{"nextPageToken":"same"},{"nextPageToken":"same"}]
        with self.assertRaisesRegex(ValueError,"pagination_cycle"):c.existing(self.policy,self.cloud,self.helper)

    def test_cloud_build_request_is_separate_bounded_and_policy_only(self):
        request=c.signing_request(REV)
        self.assertEqual(request["source"]["gitSource"]["revision"],REV)
        self.assertEqual(request["serviceAccount"],c.r.policy()["signer"])
        self.assertEqual(request["timeout"],"900s")
        self.assertIn(" attest --configuration-revision "+REV,request["steps"][0]["args"][-1])
        self.assertNotIn(" mirror",request["steps"][0]["args"][-1])
        self.assertNotIn("images",request);self.assertNotIn("substitutions",request)
        for value in ("main","a"*39,"a"*40+";evil"):
            with self.assertRaises(ValueError):c.signing_request(value)

    def test_metadata_identity_rejects_operator_or_different_attestation_account(self):
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False)
        response.read.return_value=b"wrong-account@example.invalid"
        opener=Mock();opener.open.return_value=response
        # Call the real implementation despite the default fixture patch.
        self.signer.stop()
        with patch.object(c.urllib.request,"build_opener",return_value=opener),self.assertRaisesRegex(ValueError,"signer_identity_mismatch"):
            c.signer_identity()

    def test_unreviewed_cli_configuration_fails_before_any_cloud_auth_or_mutation(self):
        for action in ("mirror","attest","submit-signing"):
            with patch.object(c,"reviewed",side_effect=ValueError("unreviewed")),patch.object(c.r,"Cloud") as cloud,patch.object(c,"copy") as copier,patch("sys.argv",["collector.py",action,"--configuration-revision",REV]),patch("sys.stdout",new=c.io.StringIO()):
                self.assertEqual(c.main(),1)
            cloud.assert_not_called();copier.assert_not_called()

    def test_cli_has_no_arbitrary_image_candidate_or_bypass_flags(self):
        for flag in ("--image","--candidate","--skip-verification","--allow-feature"):
            with patch("sys.argv",["collector.py","attest",flag,"other"]),patch("sys.stderr",new=c.io.StringIO()),self.assertRaises(SystemExit) as error:
                c.main()
            self.assertEqual(error.exception.code,2)

    def test_reviewed_main_ancestry_and_all_executing_files_are_required(self):
        source=Mock();source.blob.side_effect=lambda name:(ROOT/name).read_bytes().replace(b"\r\n",b"\n")
        fetched=Mock();fetched.__enter__=Mock(return_value=source);fetched.__exit__=Mock(return_value=False)
        with patch.object(c.r,"fetched",return_value=fetched):c.reviewed(REV)
        source.git.assert_any_call("merge-base","--is-ancestor",REV,"FETCH_HEAD")
        self.assertEqual(set(x.args[0] for x in source.blob.call_args_list),set(c.TRUST_FILES))
        source.blob.side_effect=lambda name:b"unreviewed" if name==c.SCRIPT else (ROOT/name).read_bytes().replace(b"\r\n",b"\n")
        with patch.object(c.r,"fetched",return_value=fetched),self.assertRaisesRegex(ValueError,"unreviewed_collector_files"):c.reviewed(REV)

    def test_existing_signing_build_prevents_resubmission_including_failed_build(self):
        for status in ("QUEUED","WORKING","SUCCESS","FAILURE"):
            with patch.object(c,"signing_builds",return_value=[{"id":"existing","status":status}]),patch.object(self.cloud,"request") as api:
                self.assertFalse(c.submit_signing(self.cloud,REV)["resubmitted"])
            api.assert_not_called()

    def test_uncertain_submission_recovers_build_without_blind_post(self):
        with patch.object(c,"signing_builds",side_effect=[[],[{"id":"accepted","status":"QUEUED"}]]),patch.object(self.cloud,"request",side_effect=TimeoutError()) as api:
            self.assertEqual(c.submit_signing(self.cloud,REV)["status"],"recovered_signing_builds")
        api.assert_called_once()

    def test_changed_existing_signing_build_is_rejected(self):
        build=c.signing_request(REV);build.update(id="existing",status="SUCCESS");build["steps"][0]["args"][-1]+="\necho bypass"
        with patch.object(self.cloud,"request",return_value=c.r.canonical({"builds":[build]})),self.assertRaisesRegex(ValueError,"unexpected_existing"):
            c.signing_builds(self.cloud,REV)

    def test_redirect_strips_upstream_auth_and_rejects_other_hosts(self):
        redirect=c.UpstreamRedirect();req=c.urllib.request.Request("https://ghcr.io/v2/repo/blobs/sha256:"+"0"*64,headers={"Authorization":"Bearer secret"})
        forwarded=redirect.redirect_request(req,None,302,"",{},"https://pkg-containers.githubusercontent.com/public?signature=private")
        self.assertIsNone(forwarded.get_header("Authorization"))
        for url in ("http://pkg-containers.githubusercontent.com/file","https://attacker.invalid/file"):
            with self.assertRaises(ValueError):redirect.redirect_request(req,None,302,"",{},url)

    def test_tool_cache_corruption_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/"cloudbuild/online-shop").mkdir(parents=True)
            lock=c.r.read(c.HERE/"collector-tools.json")
            asset=lock["cosign"]["windows"]
            cache=root/".local-validation/collector-tools/cosign"/lock["cosign"]["version"]/"windows";cache.mkdir(parents=True);(cache/asset["asset"]).write_bytes(b"corrupt")
            with patch.object(c,"ROOT",root),patch.object(c.platform,"system",return_value="Windows"),patch.object(c.platform,"machine",return_value="AMD64"),self.assertRaisesRegex(ValueError,"tool_cache_hash_mismatch"):
                c.tool("cosign")

    def blob_redirect(self):
        repository=self.policy["mirror_image"].split("@")[0]
        redirect=c.MirrorBlobRedirect(repository,digest(self.layer))
        route="/artifacts-downloads/namespaces/"+c.r.policy()["project"]+"/repositories/secure-delivery/downloads/Ab0123456789_-CD"
        request=c.urllib.request.Request(redirect.start,headers={"Authorization":"Basic offline-secret","Accept":"application/octet-stream",
            "Cookie":"private-cookie","Proxy-Authorization":"private-proxy","Host":"ignored-host"})
        return redirect,request,route

    def test_scoped_relative_and_absolute_blob_redirect_keep_only_same_origin_auth(self):
        redirect,request,route=self.blob_redirect()
        for location in (route,"https://"+redirect.host+route):
            with self.subTest(location=location):
                result=redirect.redirect_request(request,None,302,"",{"Location":location},"https://"+redirect.host+route)
                self.assertEqual(result.full_url,"https://"+redirect.host+route)
                self.assertEqual(result.get_header("Authorization"),"Basic offline-secret")
                self.assertEqual(result.get_header("Accept"),"application/octet-stream")
                self.assertIsNone(result.get_header("Cookie"))
                self.assertIsNone(result.get_header("Proxy-authorization"))
                self.assertIsNone(result.get_header("Host"))

    def test_blob_redirect_rejects_other_origin_scheme_port_and_userinfo_before_auth_forwarding(self):
        redirect,request,route=self.blob_redirect()
        forbidden=("http://"+redirect.host+route,"https://attacker.invalid"+route,"https://storage.googleapis.com"+route,
                   "https://"+redirect.host+".attacker.invalid"+route,"https://"+redirect.host+":444"+route,
                   "https://"+redirect.host+":443"+route,"https://user@"+redirect.host+route,"//"+redirect.host+route)
        for location in forbidden:
            with self.subTest(location=location),patch.object(c.urllib.request,"Request") as forwarded,self.assertRaisesRegex(ValueError,"collector_blob_redirect"):
                redirect.redirect_request(request,None,302,"",{"Location":location},location)
            forwarded.assert_not_called()

    def test_blob_redirect_rejects_unscoped_encoded_traversal_query_fragment_and_unknown_routes(self):
        redirect,request,route=self.blob_redirect()
        forbidden=(route.replace(c.r.policy()["project"],"another-project"),route.replace("/secure-delivery/","/another-repository/"),
                   route.replace("/downloads/","/uploads/"),route+"/extra",route+"?token=secret",route+"?",route+"#fragment",route+"#",
                   route.replace("/downloads/","/downloads/../downloads/"),route.replace("/downloads/","/downloads/%2e%2e/downloads/"),
                   route.replace("/downloads/","/downloads%2f"),route.replace("/artifacts-downloads/","/v2/"),
                   route[:-1],route+"X",route+"\n",route.replace("/downloads/","\\downloads\\"))
        for location in forbidden:
            with self.subTest(location=location),self.assertRaises(ValueError):
                redirect.redirect_request(request,None,302,"",{"Location":location},c.urllib.parse.urljoin(request.full_url,location))

    def test_blob_redirect_requires_bound_initial_get_and_one_302_hop(self):
        redirect,request,route=self.blob_redirect()
        for code in (301,303,307,308):
            with self.subTest(code=code),self.assertRaises(ValueError):redirect.redirect_request(request,None,code,"",{},route)
        for source in (request.full_url.replace("/blobs/","/manifests/"),request.full_url.replace(digest(self.layer),"sha256:"+"0"*64),
                       "https://"+redirect.host+route):
            changed=c.urllib.request.Request(source,headers={"Authorization":"Basic offline-secret"})
            with self.subTest(source=source),self.assertRaises(ValueError):redirect.redirect_request(changed,None,302,"",{},route)
        changed=c.urllib.request.Request(request.full_url,method="HEAD",headers={"Authorization":"Basic offline-secret"})
        with self.assertRaises(ValueError):redirect.redirect_request(changed,None,302,"",{},route)
        with self.assertRaises(ValueError):redirect.redirect_request(request,None,302,"",{"Location":route},route.replace("/downloads/","/uploads/"))

    def test_blob_credentials_only_go_to_exact_policy_repository_and_digest(self):
        redirect,request,route=self.blob_redirect()
        request.remove_header("Authorization")
        with self.assertRaisesRegex(ValueError,"credentials_required"):redirect.redirect_request(request,None,302,"",{},route)
        for repository in ("attacker.invalid/repo",c.r.policy()["registry"]+"/other-image"):
            with self.assertRaisesRegex(ValueError,"unapproved_collector_blob"):c.MirrorBlobRedirect(repository,digest(self.layer))
        with self.assertRaisesRegex(ValueError,"unapproved_collector_blob"):
            c.MirrorBlobRedirect(self.policy["mirror_image"].split("@")[0],"../other")

    def test_blob_bytes_builds_authenticated_get_with_collector_only_redirect_handler(self):
        self.blobs.stop()
        response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=self.layer
        opener=Mock();opener.open.return_value=response
        with patch.object(c.urllib.request,"build_opener",return_value=opener) as build:
            result=c.Mirror(self.policy,self.cloud).get("blobs",digest(self.layer))
        self.assertEqual(result,self.layer)
        self.assertIsInstance(build.call_args.args[0],c.MirrorBlobRedirect)
        request=opener.open.call_args.args[0]
        self.assertEqual(request.get_method(),"GET")
        self.assertEqual(request.full_url,build.call_args.args[0].start)
        self.assertEqual(request.get_header("Authorization"),"Basic "+c.base64.b64encode(b"oauth2accesstoken:private-token").decode())
        self.cloud.request.assert_not_called()

    def test_actual_blob_transport_bytes_still_require_exact_layer_hash_and_size(self):
        self.blobs.stop()
        for wrong_size in (False,True):
            self.make_image()
            if wrong_size:
                self.manifest["layers"][0]["size"]+=1;self.encode_manifest()
            self.reader.data=self.data
            def open_blob(request,timeout):
                identity=request.full_url.rsplit("/",1)[-1]
                raw=self.data[("blobs",identity)]
                if not wrong_size and identity==digest(self.layer):raw=b"corrupt layer bytes"
                response=Mock();response.__enter__=Mock(return_value=response);response.__exit__=Mock(return_value=False);response.read.return_value=raw
                return response
            opener=Mock();opener.open.side_effect=open_blob
            with self.subTest(wrong_size=wrong_size),patch.object(c.urllib.request,"build_opener",return_value=opener),self.assertRaisesRegex(ValueError,"collector_layer_hash"):
                c.content(c.Mirror(self.policy,self.cloud),self.policy)


if __name__ == "__main__":
    unittest.main()
