# Terraform State Bootstrap

This standalone configuration defines one protected Google Cloud Storage bucket for Terraform state and enables only the Cloud Storage API. It keeps local state until an operator explicitly authorizes provisioning.

## Safe local validation

Copy the example variables file and replace both placeholders with non-sensitive values suitable for local validation:

```shell
cp terraform.tfvars.example terraform.tfvars
terraform init -backend=false
terraform fmt
terraform validate
```

These commands initialize and validate the configuration locally. They do not create the bucket or migrate foundation state.

## Provisioning preflight

Before any separately authorized provisioning workflow, run the preflight from the repository root with all required arguments:

```shell
./scripts/preflight-foundation.sh \
  --project-id your-project-id \
  --state-bucket-name your-globally-unique-state-bucket-name \
  --state-bucket-location US
```

The command validates the inputs, required local tools, clean tracked Git state, active Google Cloud project and account, read-only project access, and both Terraform configurations. A successful run prints the project ID, project number, requested bucket name, and requested bucket location.

The preflight fails before Terraform checks when an input, tool, tracked Git state, active project, account, or project-access check is invalid. It does not enable APIs, create or change resources, inspect secrets, or write plans, state, credentials, reports, or backend configuration.

A successful preflight is not authorization to run `terraform plan`, `terraform apply`, backend initialization, or state migration. Each of those actions requires separate explicit operator authorization.

## Intended operator-authorized sequence

Creating the bucket requires a separately reviewed and explicitly authorized provisioning action. After the bucket exists, copy `terraform/foundation/backend.hcl.example` to `terraform/foundation/backend.hcl`, replace the bucket placeholder with the `state_bucket_name` output, and retain the documented prefix.

Migrating foundation state to the GCS backend also requires explicit operator authorization. From `terraform/foundation`, the future authorized migration would use:

```shell
terraform init -backend-config=backend.hcl -migrate-state
```

Bucket provisioning and state migration are not part of this change.
