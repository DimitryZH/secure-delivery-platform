import contextlib
import hashlib
import importlib.util
import json
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location("recovery", Path(__file__).parents[1] / "recovery-kit.py")
r = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)


class Response:
    def __init__(self, body):
        self.body = body

    def iter_content(self, size):
        yield self.body


class RecoveryKitTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.data = {}
        self.calls = []

    def descriptor(self, body, media="application/octet-stream"):
        digest = "sha256:" + hashlib.sha256(body).hexdigest()
        self.data[digest] = body
        return {"digest": digest, "size": len(body), "mediaType": media}

    def manifest(self, value, media):
        return self.descriptor(json.dumps({"schemaVersion": 2, "mediaType": media, **value}).encode(), media)

    def graph(self):
        layer = self.descriptor(b"complete compressed layer")
        config = self.descriptor(b'{"architecture":"amd64","os":"linux"}')
        media = "application/vnd.oci.image.manifest.v1+json"
        amd = self.manifest({"config": config, "layers": [layer]}, media)
        arm = self.manifest({"config": self.descriptor(b'{"architecture":"arm64"}'), "layers": [layer]}, media)
        index = self.manifest({"manifests": [amd, arm]}, "application/vnd.oci.image.index.v1+json")
        return "region-docker.pkg.dev/example-project/release/app@" + index["digest"], layer

    @contextlib.contextmanager
    def fetch(self, image, kind, digest):
        self.calls.append(digest)
        yield Response(self.data[digest])

    def test_every_platform_config_layer_preserved_and_deduplicated(self):
        image, layer = self.graph()
        result = r.export_images([image], self.root / "images", self.fetch)
        self.assertEqual((result["images"], result["blobs"]), (1, 6))
        self.assertEqual(self.calls.count(layer["digest"]), 1)
        self.assertEqual(r.verify_oci(self.root / "images")["references"], [image])

    def test_missing_or_corrupt_layer_fails_offline(self):
        image, layer = self.graph()
        r.export_images([image], self.root / "images", self.fetch)
        path = r.blob_path(self.root / "images", layer["digest"])
        path.write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            r.verify_oci(self.root / "images")
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            r.verify_oci(self.root / "images")

    def test_download_digest_mismatch_fails(self):
        image, layer = self.graph()
        self.data[layer["digest"]] = b"bad response"
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            r.export_images([image], self.root / "images", self.fetch)

    def test_mutable_tags_and_path_traversal_rejected(self):
        for name in ["region-docker.pkg.dev/example/release/app:latest", "https://untrusted/image"]:
            with self.assertRaises(ValueError):
                r.export_images([name], self.root / "images", self.fetch)
        for name in ["../outside", "C:/outside", "a\\..\\b", "/absolute"]:
            with self.assertRaises(ValueError):
                r.local_path(self.root, name)

    def test_kit_files_and_image_coverage_are_closed(self):
        image, _ = self.graph()
        r.export_images([image], self.root / "images", self.fetch)
        manifest = {"version": 1, "required_images": [image], "files": {
            p.relative_to(self.root).as_posix(): {"digest": r.digest_file(p), "size": p.stat().st_size}
            for p in self.root.rglob("*") if p.is_file()}}
        path = self.root / "kit-manifest.json"
        path.write_text(json.dumps(manifest))
        self.assertEqual(r.verify_kit(self.root)["images"], 1)
        manifest["required_images"] = []
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(ValueError, "coverage"):
            r.verify_kit(self.root)
        manifest["required_images"] = [image]
        path.write_text(json.dumps(manifest))
        (self.root / "unlisted").write_text("not covered")
        with self.assertRaisesRegex(ValueError, "unlisted"):
            r.verify_kit(self.root)

    def test_foreign_layer_is_not_silently_skipped(self):
        layer = self.descriptor(b"layer")
        layer["urls"] = ["https://elsewhere.invalid/blob"]
        config = self.descriptor(b"{}")
        desc = self.manifest({"config": config, "layers": [layer]}, "application/vnd.oci.image.manifest.v1+json")
        image = "region-docker.pkg.dev/example-project/release/app@" + desc["digest"]
        with self.assertRaisesRegex(ValueError, "external/foreign"):
            r.export_images([image], self.root / "images", self.fetch)

    def test_unknown_index_children_cannot_hide_an_incomplete_graph(self):
        desc = self.manifest({"manifests": [self.descriptor(b"opaque")]}, "application/vnd.oci.image.index.v1+json")
        with self.assertRaisesRegex(ValueError, "index child"):
            r.export_images(["region-docker.pkg.dev/example-project/release/app@" + desc["digest"]], self.root / "images", self.fetch)

    def registry_case(self, location):
        origin = "https://region-docker.pkg.dev/v2/example-project/release/app/blobs/sha256:" + "a" * 64
        first = Mock(status_code=302, headers={"Location": location}, url=origin)
        second = Mock(status_code=200)
        session = Mock()
        session.get.side_effect = [first, second]
        with patch.dict("sys.modules", {"requests": types.SimpleNamespace(Session=lambda: session)}):
            registry = r.Registry("in-memory-test-token")
        return registry, session, first, second

    def test_relative_same_origin_scoped_blob_redirect(self):
        path = "/artifacts-downloads/namespaces/example-project/repositories/release/downloads/abcdefghijklmnop"
        registry, session, first, second = self.registry_case(path)
        image = "region-docker.pkg.dev/example-project/release/app@sha256:" + "a" * 64
        self.assertIs(registry(image, "blobs", "sha256:" + "a" * 64), second)
        first.close.assert_called_once()
        self.assertEqual(session.get.call_args.args[0], "https://region-docker.pkg.dev" + path)
        self.assertEqual(session.get.call_args.kwargs["auth"], ("oauth2accesstoken", "in-memory-test-token"))
        self.assertFalse(session.get.call_args.kwargs["allow_redirects"])

    def test_redirect_cannot_leak_token_to_other_origin_or_repository(self):
        for target in ["https://elsewhere.invalid/blob", "/other", "/artifacts-downloads/namespaces/other/repositories/release/downloads/abcdefghijklmnop"]:
            registry, session, first, _ = self.registry_case(target)
            with self.assertRaisesRegex(ValueError, "unexpected registry redirect"):
                registry("region-docker.pkg.dev/example-project/release/app@sha256:" + "a" * 64, "blobs", "sha256:" + "a" * 64)
            self.assertEqual(session.get.call_count, 1)
            first.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
