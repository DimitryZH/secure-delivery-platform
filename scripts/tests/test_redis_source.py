"""Official Redis source, content and two-hop mirror verification regressions."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("redis_source_test", ROOT / "cloudbuild/online-shop/redis.py")
redis = importlib.util.module_from_spec(spec); spec.loader.exec_module(redis)


class OfficialRedisTests(unittest.TestCase):
    def bundle(self, mutate=lambda stage, value: None):
        q = copy.deepcopy(redis.policy()); records = {}; source_files = {}
        def store(kind, value):
            raw = redis.r.canonical(value) if not isinstance(value, bytes) else value
            descriptor = {"digest": "sha256:" + redis.r.sha(raw), "size": len(raw)}
            records[kind, descriptor["digest"]] = raw
            return descriptor
        config = {"os":"linux", "architecture":"amd64", "config":{"Env":["REDIS_VERSION="+q["redis_version"]],
            "WorkingDir":"/data", "Entrypoint":["docker-entrypoint.sh"], "Cmd":["redis-server"]}}
        mutate("config", config); desc = store("blobs", config); q["config_digest"] = desc["digest"]
        layer = store("blobs", b"compressed fixture")
        manifest = {"schemaVersion":2, "config":desc, "layers":[layer]}
        mutate("manifest", manifest); platform = store("manifests", manifest); q["manifest_digest"] = platform["digest"]
        source = q["producing_source"]; build = q["producing_build"]; uri = source["repository"] + ".git#" + source["revision"]
        statement = {"_type":"https://in-toto.io/Statement/v0.1", "predicateType":"https://slsa.dev/provenance/v0.2",
            "subject":[{"name":"pkg:docker/redis@"+q["discovery_selector"]+"?platform=linux%2Famd64", "digest":{"sha256":q["manifest_digest"][7:]}}],
            "predicate":{"builder":{"id":build["builder_id"]}, "buildType":build["build_type"], "metadata":{"buildInvocationID":build["id"]},
                "invocation":{"configSource":{"uri":uri+":alpine", "entryPoint":"Dockerfile"}, "environment":{"platform":"linux/amd64"}},
                "materials":[{"uri":uri, "digest":{"sha1":source["revision"]}}]}}
        mutate("provenance", statement); descriptor = store("blobs", statement)
        descriptor["annotations"] = {"in-toto.io/predicate-type":"https://slsa.dev/provenance/v0.2"}
        q["source_proof"]["statement"] = descriptor; build["statement_digest"] = descriptor["digest"]
        attestation = {"schemaVersion":2, "layers":[descriptor]}; mutate("attestation", attestation)
        attested = store("manifests", attestation)
        attested.update(platform={"os":"unknown", "architecture":"unknown"}, annotations={"vnd.docker.reference.digest":q["manifest_digest"], "vnd.docker.reference.type":"attestation-manifest"})
        q["source_proof"]["attestation_manifest"] = attested
        platform["platform"] = {"os":"linux", "architecture":"amd64"}
        index = {"schemaVersion":2, "manifests":[platform, attested]}; mutate("index", index)
        q["index_digest"] = store("manifests", index)["digest"]
        meta = q["source_proof"]["official_images"]
        text = "GitRepo: " + source["repository"] + ".git\n\nTags: " + q["discovery_selector"] + "\nArchitectures: amd64\nGitCommit: " + source["revision"] + "\nDirectory: alpine\n"
        data = {"text":text}; mutate("metadata", data); raw = data["text"].encode()
        meta["sha256"] = "sha256:" + redis.r.sha(raw); source_files[meta["repository"],meta["revision"],meta["path"]] = raw
        for path in source["filesSha256"]:
            raw = ("fixture-"+path).encode(); source["filesSha256"][path] = "sha256:"+redis.r.sha(raw)
            source_files[source["repository"],source["revision"],path] = raw
        read = Mock(); read.get.side_effect = lambda kind,digest: records[kind,digest]
        return q,read,source_files,records

    def test_complete_official_source_platform_build_and_content_positive(self):
        q,read,files,_ = self.bundle()
        proof = redis.official_source(q,read,lambda *key:files[key])
        self.assertEqual(proof["source_association"],"verified");self.assertFalse(proof["publisher_signature_verified"])
        self.assertEqual(redis.content(read,q)["layers_verified"],1)

    def test_wrong_subject_source_build_and_platform_fail_even_with_recomputed_hashes(self):
        mutations = [
            ("provenance",lambda p:p["subject"][0].update(digest={"sha256":"0"*64})),
            ("provenance",lambda p:p["predicate"]["builder"].update(id="https://unapproved.example/builder")),
            ("provenance",lambda p:p["predicate"]["metadata"].update(buildInvocationID="other")),
            ("provenance",lambda p:p["predicate"]["invocation"]["configSource"].update(uri="unapproved-source")),
            ("provenance",lambda p:p["predicate"]["invocation"]["environment"].update(platform="linux/arm64")),
            ("provenance",lambda p:p["predicate"].update(materials=[])),
            ("index",lambda p:p["manifests"].append(copy.deepcopy(p["manifests"][0]))),
            ("index",lambda p:p["manifests"][1]["annotations"].update({"vnd.docker.reference.digest":"sha256:"+"0"*64})),
            ("metadata",lambda p:p.update(text=p["text"].replace("Directory: alpine","Directory: debian"))),
            ("metadata",lambda p:p.update(text=p["text"].replace("Architectures: amd64","Architectures: arm64v8")))]
        for stage,mutation in mutations:
            q,read,files,_ = self.bundle(lambda name,obj:mutation(obj) if name==stage else None)
            with self.subTest(stage=stage,mutation=mutation),self.assertRaises(ValueError):redis.official_source(q,read,lambda *key:files[key])

    def test_wrong_config_version_platform_and_blob_hash_size_rejected(self):
        for stage,mutate in (("config",lambda p:p.update(architecture="arm64")),
            ("config",lambda p:p["config"].update(Env=["REDIS_VERSION=7.4.8"])),
            ("manifest",lambda p:p.update(schemaVersion=True)),
            ("manifest",lambda p:p["layers"][0].update(size=p["layers"][0]["size"]+1)),
            ("manifest",lambda p:p["layers"][0].update(urls=["https://unapproved.example/blob"]))):
            q,read,_,_ = self.bundle(lambda name,obj:mutate(obj) if name==stage else None)
            with self.assertRaises(ValueError):redis.content(read,q)
        q,read,_,records = self.bundle()
        key=next(key for key in records if records[key]==b"compressed fixture");records[key]=b"wrong layer"
        with self.assertRaises(ValueError):redis.content(read,q)

    def test_source_file_and_index_bytes_must_match_pins(self):
        q,read,files,records = self.bundle()
        with self.assertRaises(ValueError):redis.official_source(q,read,lambda *key:files[key]+b"changed")
        records["manifests",q["index_digest"]]+=b"changed"
        with self.assertRaises(ValueError):redis.official_source(q,read,lambda *key:files[key])

    def test_unmerged_contract_or_failed_canonical_mirror_prevents_chain_success(self):
        q,read,_,_ = self.bundle()
        with patch.object(redis,"contracts",side_effect=subprocess.CalledProcessError(1,["git","merge-base"])),patch.object(redis,"upstream") as upstream:
            with self.assertRaises(subprocess.SubprocessError):redis.verify_chain(q,Mock())
            upstream.assert_not_called()
        with patch.object(redis,"contracts"),patch.object(redis,"upstream",return_value={"status":"official_source_content_verified"}),\
             patch.object(redis,"reader") as factory:
            factory.return_value.__enter__.side_effect=ValueError("canonical digest unavailable")
            with self.assertRaises(ValueError):redis.verify_chain(q,Mock())
            self.assertEqual(factory.call_count,1);self.assertEqual(factory.call_args.args[0],q["selection_repository"])

    def test_both_mirrors_are_independently_read_before_chain_verified(self):
        q,read,_,_ = self.bundle()
        with patch.object(redis,"contracts"),patch.object(redis,"upstream",return_value={"publisher_signature_verified":False}),patch.object(redis,"reader") as factory:
            factory.return_value.__enter__.return_value=read
            result=redis.verify_chain(q,Mock())
            self.assertEqual(result["status"],"redis_chain_verified");self.assertFalse(result["publisher_signature_verified"])
            self.assertEqual([call.args[0] for call in factory.call_args_list],[q["selection_repository"],redis.r.policy()["registry"]+q["intended_mirror_suffix"]])
            self.assertEqual(read.get.call_count,6)  # manifest, config, layer for EACH mirror

    def test_public_reader_is_anonymous_and_registry_login_is_host_scoped_stdin(self):
        q=redis.policy();cloud=Mock(token="offline-fixture-token")
        with patch.object(redis.support,"tool",return_value="pinned-crane"),patch.object(redis.support,"run",return_value=b"{}") as run:
            with redis.reader(q["upstream_repository"],q) as read:read.get("manifests",q["index_digest"])
            self.assertEqual(run.call_count,1);self.assertNotIn("auth",run.call_args.args[0])
            self.assertIn("@"+q["index_digest"],run.call_args.args[0][-1])
            run.reset_mock()
            with redis.reader(redis.r.policy()["registry"]+q["intended_mirror_suffix"],q,cloud) as read:read.get("blobs",q["config_digest"])
            login=run.call_args_list[0];self.assertEqual(login.args[0][3],"us-central1-docker.pkg.dev")
            self.assertIn("--password-stdin",login.args[0]);self.assertEqual(login.kwargs["input"],b"offline-fixture-token\n")
            self.assertNotIn("offline-fixture-token",str(login.args))
        with self.assertRaises(ValueError),patch.object(redis.support,"run") as run:
            with redis.reader("docker.io/unapproved/redis",q):pass
        run.assert_not_called()

    def test_source_transport_rejects_unapproved_url_and_redirect(self):
        with self.assertRaises(ValueError):redis.source_bytes("https://unapproved.example/source","a"*40,"alpine/Dockerfile")
        with self.assertRaises(ValueError):redis.NoRedirect().redirect_request(None,None,302,"",{},"http://unapproved.example")

    @unittest.skipUnless(os.environ.get("SDP_REDIS_EVIDENCE_DIRECTORY"),"optional actual public registry/source byte fixture")
    def test_actual_selected_upstream_bytes_and_source_fixtures(self):
        path=Path(os.environ["SDP_REDIS_EVIDENCE_DIRECTORY"]);q=redis.policy()
        records={}
        for name in ("upstream-index.private.json","upstream-manifest.private.json","upstream-attestation-manifest-0.private.json"):
            raw=(path/name).read_bytes();records["manifests","sha256:"+redis.r.sha(raw)]=raw
        for name in ("upstream-config.private.json","upstream-attestation-0-1.private.json",*["layer-"+str(i)+".private.tar.gz" for i in range(7)]):
            raw=(path/name).read_bytes();records["blobs","sha256:"+redis.r.sha(raw)]=raw
        read=Mock();read.get.side_effect=lambda kind,digest:records[kind,digest]
        def fetch(repository,revision,name):
            return (path/("official-library-redis.private.txt" if name=="library/redis" else "official-"+name.split("/")[-1]+".private")).read_bytes()
        self.assertEqual(redis.official_source(q,read,fetch)["source_association"],"verified")
        self.assertEqual(redis.content(read,q)["layers_verified"],7)


if __name__=="__main__":unittest.main()
