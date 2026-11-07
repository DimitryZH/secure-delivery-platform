"""Local regressions for the bounded Online Shop synthetic and source artifact."""
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "monitoring/online-shop/synthetic"


class ShopSyntheticTests(unittest.TestCase):
    def test_source_archive_is_reproducible_and_cannot_overwrite(self):
        spec = importlib.util.spec_from_file_location("synthetic_packager", SOURCE / "package-source.py")
        packager = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(packager)
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            self.assertEqual(packager.package(first), packager.package(second))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(set(archive.namelist()), set(packager.SOURCE_FILES))
                manifest = json.loads(archive.read("package.json"))
                lock = json.loads(archive.read("package-lock.json"))
                self.assertEqual(manifest["dependencies"], lock["packages"][""]["dependencies"])
                self.assertEqual(archive.read("journey.js"), (SOURCE / "journey.js").read_bytes())
            with self.assertRaises(FileExistsError):
                packager.package(first)

    @unittest.skipUnless(shutil.which("node"), "Node.js required for synthetic regressions")
    def test_journey_budget_partial_failure_and_cleanup(self):
        result = subprocess.run(
            ["node", "--test", str(SOURCE / "journey.test.js")],
            capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
