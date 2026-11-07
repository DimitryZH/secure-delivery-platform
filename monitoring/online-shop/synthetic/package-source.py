"""Create a deterministic synthetic source archive for the reviewed Terraform plan."""
import argparse
import hashlib
from pathlib import Path
import zipfile

SOURCE_FILES = ("index.js", "journey.js", "package.json", "package-lock.json")


def package(destination):
    source = Path(__file__).resolve().parent
    with zipfile.ZipFile(destination, "x", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in SOURCE_FILES:
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, (source / name).read_bytes())
    return hashlib.sha256(Path(destination).read_bytes()).hexdigest()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(package(args.destination))
