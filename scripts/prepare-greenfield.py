"""Generate/check ignored execution roots from an explicit canonical source allowlist.
No Terraform invocation, credentials, cloud calls, state copying or migration.
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ENV = REPO / ".local-validation/environments/sdp-gcp"
FOUNDATION = "main.tf variables.tf versions.tf service-accounts.tf outputs.tf gke.tf complete-shop.tf clouddeploy.tf cloudbuild.tf catalog-verification-iam.tf catalog-runtime.tf binary-authorization.tf attestation.tf dashboard.tf alert-policy.tf.json logging-metrics.tf.json .terraform.lock.hcl".split()
BOOTSTRAP = "main.tf variables.tf versions.tf outputs.tf .terraform.lock.hcl".split()
QUERIES = "request-rate error-rate p95-latency observed-availability available-replicas desired-replicas".split()

def expected():
    result = {}
    excluded = {"kubernetes.tf", "legacy-default-pool-import.tf", "shop-endpoint.tf", "shop-observability.tf"}
    actual = {p.name for p in (REPO / "terraform/foundation").iterdir() if p.name.endswith((".tf", ".tf.json"))}
    if actual != (set(FOUNDATION) - {".terraform.lock.hcl"}) | excluded:
        raise SystemExit("Canonical foundation composition changed; review the allowlist.")
    for module, allowed in [("bootstrap", set(BOOTSTRAP) - {".terraform.lock.hcl"}), ("kubernetes", {"main.tf"})]:
        actual = {p.name for p in (REPO / "terraform" / module).iterdir() if p.name.endswith((".tf", ".tf.json"))}
        if actual != allowed:
            raise SystemExit(f"Canonical {module} composition changed; review the allowlist.")
    for root, names in [("bootstrap", BOOTSTRAP), ("foundation", FOUNDATION)]:
        for name in names:
            result[f"terraform/{root}/{name}"] = (REPO / f"terraform/{root}/{name}").read_bytes()
    for name in ["main.tf"]:
        result[f"terraform/kubernetes/{name}"] = (REPO / f"terraform/kubernetes/{name}").read_bytes()
    # Reuse the reviewed provider selections; init must use -lockfile=readonly.
    lock = (REPO / "terraform/foundation/.terraform.lock.hcl").read_text()
    blocks = re.findall(r'provider "registry.terraform.io/hashicorp/(google|kubernetes)" \{.*?^\}', lock, re.S | re.M)
    selected = re.findall(r'provider "registry.terraform.io/hashicorp/(?:google|kubernetes)" \{.*?^\}', lock, re.S | re.M)
    if sorted(blocks) != ["google", "kubernetes"]:
        raise SystemExit("Expected reviewed google/kubernetes lock entries")
    result["terraform/kubernetes/.terraform.lock.hcl"] = ("\n\n".join(selected) + "\n").encode()
    templates = ["sample-service-health.json.tftpl", "online-shop-dev/dashboard.json.tftpl"] + [f"online-shop-dev/queries/{q}.promql.tftpl" for q in QUERIES]
    for name in templates:
        path = f"monitoring/dashboards/{name}"
        result[path] = (REPO / path).read_bytes()
    result["terraform/foundation/greenfield-disabled.tf"] = (REPO / "terraform/greenfield/disabled-features.tf").read_bytes()
    result["terraform/foundation/greenfield_override.tf"] = (REPO / "terraform/greenfield/greenfield_override.tf").read_bytes()
    state = (ENV.resolve() / "state/bootstrap/terraform.tfstate").as_posix()
    result["terraform/bootstrap/backend.tf"] = ('terraform {\n  backend "local" {\n    path = ' + json.dumps(state) + '\n  }\n}\n').encode()
    return result

def materialize(check=False):
    root = ENV / "roots"
    if root.is_symlink() or root.resolve() != ENV.resolve() / "roots":
        raise SystemExit("Execution root must not redirect outside the isolated environment")
    files = expected()
    manifest = json.dumps({p: hashlib.sha256(b).hexdigest() for p, b in sorted(files.items())}, indent=2).encode() + b"\n"
    files["manifest.json"] = manifest
    existing = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()} if root.exists() else set()
    # Provider caches belong in TF_DATA_DIR, not execution roots. Reject any extra file.
    extra = existing - files.keys()
    if extra:
        raise SystemExit("Unexpected execution-root files (not removed): " + ", ".join(sorted(extra)))
    # Reject nested links/junctions too; never overwrite a redirected source/state.
    for rel in files:
        if (root / rel).resolve() != root.resolve() / rel:
            raise SystemExit("Redirected generated file/directory: " + rel)
    for rel, content in files.items():
        target = root / rel
        if check:
            if not target.is_file() or target.read_bytes() != content:
                raise SystemExit("Stale/missing generated input: " + rel)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    print(("Verified" if check else "Generated") + f" {len(files)-1} files; no private inputs/state/backend metadata copied.")

def check_execution(name, environ=None):
    """Read-only pre-operation guard. Never invokes Terraform or authenticates."""
    e = os.environ if environ is None else environ
    forbidden = [k for k in e if k.startswith(("TF_VAR_", "TF_CLI_ARGS"))]
    forbidden += [k for k in e if k.startswith("GOOGLE_") and k != "GOOGLE_APPLICATION_CREDENTIALS"]
    forbidden += [k for k in e if k.startswith("CLOUDSDK_") and k not in {"CLOUDSDK_CONFIG", "CLOUDSDK_CORE_ACCOUNT", "CLOUDSDK_CORE_PROJECT"}]
    if forbidden:
        raise SystemExit("Remove inherited Terraform/auth overrides: " + ", ".join(sorted(forbidden)))
    expected_data = (ENV / "tfdata" / name).resolve()
    def same_path(value, path):
        return bool(value) and Path(value).resolve() == path.resolve()
    if not same_path(e.get("TF_DATA_DIR"), expected_data) or e.get("TF_WORKSPACE") != "default":
        raise SystemExit("Require isolated root-specific TF_DATA_DIR and TF_WORKSPACE=default")
    # Operator identity is private input, never a tracked email literal.
    private = (ENV / "foundation.tfvars").read_text()
    operators = re.findall(r'^deployment_operator_principal\s*=\s*"user:([^"\s]+)"\s*$', private, re.M)
    if len(operators) != 1:
        raise SystemExit("Require one explicit human operator in approved private foundation inputs")
    # Authentication paths are local operator settings, not public source data.
    settings = json.loads((ENV / "execution-settings.private.json").read_text(encoding="utf-8"))
    if set(settings) != {"version", "sdk_config_directory"} or type(settings["version"]) is not int or settings["version"] != 1:
        raise SystemExit("Require reviewed private execution settings version 1")
    adc_dir = Path(settings["sdk_config_directory"])
    if not adc_dir.is_absolute():
        raise SystemExit("Require an absolute isolated SDK configuration directory")
    adc = adc_dir / "application_default_credentials.json"
    if not same_path(e.get("GOOGLE_APPLICATION_CREDENTIALS"), adc) or not adc.is_file():
        raise SystemExit("Require the approved isolated ADC file; credential contents are not read")
    if not same_path(e.get("CLOUDSDK_CONFIG"), adc_dir) or e.get("CLOUDSDK_CORE_ACCOUNT") != operators[0] or e.get("CLOUDSDK_CORE_PROJECT") != "sdp-gcp":
        raise SystemExit("Require isolated SDK directory and explicit new account/project")
    # A reused TF_DATA_DIR may hide backend ownership even when roots are clean.
    metadata = expected_data / "terraform.tfstate"
    if metadata.exists():
        backend = json.loads(metadata.read_text())["backend"]
        config = backend.get("config", {})
        if any(config.get(k) for k in ["credentials", "access_token", "impersonate_service_account", "impersonate_service_account_delegates"]):
            raise SystemExit("Cached backend credential overrides are forbidden")
        if name == "bootstrap":
            valid = backend.get("type") == "local" and same_path(config.get("path"), ENV / "state/bootstrap/terraform.tfstate") and not config.get("workspace_dir")
        else:
            prefix = "secure-delivery-platform/" + ("foundation" if name == "foundation" else "kubernetes")
            valid = backend.get("type") == "gcs" and config.get("bucket") == "sdp-gcp-738317279206-tf-state" and config.get("prefix") == prefix
        if not valid:
            raise SystemExit("Cached backend does not match the isolated environment; do not migrate it")
    materialize(check=True)
    print("Execution environment and cached backend guard passed; no cloud access performed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--check-execution", choices=["bootstrap", "foundation", "kubernetes"])
    args = parser.parse_args()
    if args.check_execution:
        check_execution(args.check_execution)
    else:
        materialize(args.check)
