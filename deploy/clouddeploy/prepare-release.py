#!/usr/bin/env python3
"""Prepare a local Cloud Deploy source bundle; never call cloud or build tools."""
import argparse
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("deployment", ROOT / "deploy/deploy-release.py")
deployment = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(deployment)


def prepare(metadata, output, reviewed=False):
    policy = deployment.load(ROOT / "deploy/environments.json")
    record = deployment.load(metadata)
    # Validate the original target as well as the derived target-specific views.
    deployment.validate(record, policy, record.get("target_environment"), reviewed)
    documents = {}
    for environment in ("dev", "stage", "prod"):
        target = {**record, "target_environment": environment}
        deployment.validate(target, policy, environment, reviewed)
        documents[environment] = deployment.render(target, policy, environment)
    # Validate every environment before writing any bundle; a bundle is one digest.
    output = Path(output)
    if output.exists():
        raise ValueError("output_directory_must_not_exist")
    output.mkdir(parents=True)
    (output / "skaffold.yaml").write_text(
        (Path(__file__).parent / "skaffold.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    for environment, manifest in documents.items():
        directory = output / "rendered" / environment
        directory.mkdir(parents=True)
        (directory / "sample-service.yaml").write_text(manifest, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--reviewed", action="store_true",
                        help="Confirm review of stage/prod preparation; does not approve a rollout")
    args = parser.parse_args()
    try:
        prepare(args.metadata, args.output_dir, args.reviewed)
    except (OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "Cloud Deploy bundle preparation failed; check metadata, review, and output directory.\n")
    print("Prepared local source bundle; no build, release, rollout, or deployment performed.")


if __name__ == "__main__":
    main()
