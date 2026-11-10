# Terraform Foundation

This directory manages the shared Google Cloud/GKE infrastructure with explicit resources rather than a reusable platform framework.

## Configuration inventory

- `main.tf`: provider settings, baseline APIs, Artifact Registry repository.
- `service-accounts.tf`: build/deploy/node/reviewer accounts and scoped bindings.
- `cloudbuild.tf`: sample image-build trigger.
- `gke.tf`: cluster and explicitly managed node pools.
- `kubernetes.tf`: namespaces/provider retained in the existing combined root.
- `legacy-default-pool-import.tf`: adoption of an existing default pool in the combined root.
- `attestation.tf`: separate signer, KMS key, note/attestor, signing IAM, and attestation source bucket.
- `binary-authorization.tf`: protected cluster admission policy.
- `clouddeploy.tf`: API, Job Runner binding, serial pipeline/targets, and source/render artifact bucket.
- `logging-metrics.tf.json`: three structured sample-service request/error/latency metrics.
- `dashboard.tf`: one deployment health dashboard using existing metrics.
- `alert-policy.tf.json`: one availability review policy using existing deployment-state gauges.
- `outputs.tf`: resource identities and integration outputs.

Resources here define the bounded [release-health log-based metrics](../../monitoring/log-based-metrics/README.md), one [deployment health dashboard](../../monitoring/dashboards/README.md), and one [availability alert policy](../../monitoring/alert-policies/README.md). The availability alert policy is deployed and live-validated in its healthy state. Future Terraform mutations require a reviewed plan and explicit apply authorization. [IAM Model](../../docs/iam-model.md) owns the identity/authority matrix; [Trusted Delivery](../../docs/trusted-delivery.md) owns delivery and storage contracts.

## Validation and backend

Terraform requires version 1.6 or later and the repository provider constraints/lock. Supply project/operator inputs privately in ignored files or the local session. For validation without backend initialization:

```sh
terraform init -backend=false
terraform fmt -check
terraform validate
```

The configured backend is GCS. For an existing reviewed backend, use an ignored `backend.hcl` based on `backend.hcl.example`, with `<TF_STATE_BUCKET>` and the existing `secure-delivery-platform/foundation` prefix. Backend initialization and any initial migration are separately authorized operations; never migrate an established backend as validation.

Use fresh locked plans and explicit apply authorization as described in [Operator Runbook](../../docs/operator-runbook.md#infrastructure-and-credential-safety). State and binary/JSON plans can contain private inputs; never commit them. [Bootstrap](../bootstrap/README.md) owns initial state-bucket setup.

## Provider quota requirement

The Google provider sets `user_project_override=true` and `billing_project=var.project_id`, sending the target project as the quota/billing project for provider requests. The authenticated caller needs `serviceusage.services.use` on that project. This setting grants no permissions or API enablement; the GCS backend credentials/configuration are separate.

See [provider quota configuration](https://registry.terraform.io/providers/hashicorp/google/5.45.2/docs/guides/provider_reference#quota-management-configuration). Keep the current quota setting without reproducing credential-consumer identifiers or historical troubleshooting output.

## Isolated execution roots

For a new environment, use `python scripts/prepare-greenfield.py` to generate execution snapshots from canonical Terraform sources. The generator's reviewed profile selects the environment directory; generated files are not an independently maintained Terraform copy. Its explicit allowlist includes required dashboard templates and provider lock entries, excludes private inputs/caches/plans, and writes a SHA-256 manifest. Endpoint and synthetic provisioning are excluded from this initial profile. Changing that scope requires review.

Run `python scripts/prepare-greenfield.py --check` after generation and after any source edit. Unexpected files, redirected paths and stale snapshots fail closed. Before each separately authorized plan/apply, run `python scripts/prepare-greenfield.py --check-execution <ROOT>` in the same process, where `<ROOT>` is `bootstrap`, `foundation` or `kubernetes`. The guard checks snapshot freshness, the profile's isolated authentication selection, root-specific data directory, workspace and cached backend identity. It does not authenticate, invoke Terraform or prevent a later command from supplying different arguments.

Use absolute paths for `<ENV_ROOT>`, private var-files and backend settings. Each root needs its own `TF_DATA_DIR=<ENV_ROOT>/tfdata/<ROOT>` and workspace `default`. Explicitly select approved ADC credentials; inherited Terraform arguments, variable overrides and credential overrides must be cleared. Do not copy an existing `.terraform` directory or automatically loaded tfvars into generated roots.

Keep the approved authentication location in ignored `<ENV_ROOT>/execution-settings.private.json`: `{"version":1,"sdk_config_directory":"<ABSOLUTE_ISOLATED_SDK_DIRECTORY>"}`. The guard requires that directory to match `CLOUDSDK_CONFIG` and its `application_default_credentials.json` to match `GOOGLE_APPLICATION_CREDENTIALS`; it does not read credential contents. This file stays outside generated roots and must not be published.

`TF_DATA_DIR` does not relocate local state. The generated bootstrap root declares an absolute local backend path `<ENV_ROOT>/state/bootstrap/terraform.tfstate`. Foundation uses a separately reviewed new GCS backend. Kubernetes requires a distinct backend prefix; never reuse foundation state or migrate historical state into a new environment.

Ownership and ordering:

1. Bootstrap owns the state bucket and Storage API.
2. Cloud foundation owns APIs, IAM, registry, trust, storage, cluster and node pools. Its generated root excludes the Kubernetes provider and namespace resources.
3. The separate Kubernetes root owns namespaces. Pass the exact sensitive `kubernetes_connection` output as private `cloud_connection` input, plus matching project ID. Treat state and output transport as private; never publish endpoint/CA output or tokens. A working cluster is required before planning this root.
4. Restore verified artifacts and reviewed delivery contracts before deployment. Existing attestations do not authorize different registry URIs.

For greenfield pools, the temporary cluster-created pool is removed before the separately managed default pool is created. Historical adoption remains in the combined root; do not apply that import to a nonexistent pool. The singleton Binary Authorization import is retained: after separately authorized API enablement, confirm the project policy exists before planning its import. If absent, review creation semantics rather than deleting the import automatically.

Other prerequisites include state-bucket name availability, API/quota/IAM review, node/surge capacity and the GitHub connection/repository referenced by the sample-service trigger. That connection is not created by this Terraform. Offline validation is not a live readiness check. Separate persistent/runtime lifecycle management remains future work; controller-owned Gateway/load-balancer resources must be removed before cluster teardown.
