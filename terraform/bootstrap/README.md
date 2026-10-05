# Terraform State Bootstrap

This standalone configuration manages the Cloud Storage API and a Terraform state bucket with uniform bucket-level access, public access prevention, versioning enabled, and `force_destroy=false`. Bootstrap state is local; foundation uses its separate GCS backend.

## Local validation

From this directory, copy `terraform.tfvars.example` to an ignored local variables file and privately supply the project/bucket inputs:

```sh
terraform init -backend=false
terraform fmt -check
terraform validate
```

These checks do not provision the bucket or migrate state.

## Provisioning preflight and backend setup

From the repository root:

```sh
./scripts/preflight-foundation.sh \
  --project-id <PROJECT_ID> \
  --state-bucket-name <TF_STATE_BUCKET> \
  --state-bucket-location <STATE_BUCKET_LOCATION>
```

The preflight checks inputs/tools, clean tracked Git state, active project/account, read-only project access, and Terraform configurations. It performs no resource mutation or plan/state/backend writes. Its output contains project identifiers; keep raw output private. Success does not authorize planning, apply, initialization, or migration.

For a separately authorized initial setup, use the bucket output in the ignored foundation `backend.hcl`, retaining `secure-delivery-platform/foundation`. Initial state migration requires separate authorization:

```sh
terraform -chdir=terraform/foundation init -backend-config=backend.hcl -migrate-state
```

Do not repeat migration for an already initialized backend as housekeeping. See [foundation guidance](../foundation/README.md) and [infrastructure safety](../../docs/operator-runbook.md#infrastructure-and-credential-safety).
