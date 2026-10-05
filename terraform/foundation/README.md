# Terraform Foundation

This directory manages the shared Google Cloud/GKE infrastructure with explicit resources rather than a reusable platform framework.

## Configuration inventory

- `main.tf`: provider settings, baseline APIs, Artifact Registry repository.
- `service-accounts.tf`: build/deploy/node/reviewer accounts and scoped bindings.
- `cloudbuild.tf`: sample image-build trigger.
- `gke.tf`: cluster and dev/stage/prod namespaces.
- `attestation.tf`: separate signer, KMS key, note/attestor, signing IAM, and attestation source bucket.
- `binary-authorization.tf`: protected cluster admission policy.
- `clouddeploy.tf`: API, Job Runner binding, serial pipeline/targets, and source/render artifact bucket.
- `outputs.tf`: resource identities and integration outputs.

Resources here do not define application dashboards, alert policies, or log-based metrics. [IAM Model](../../docs/iam-model.md) owns the identity/authority matrix; [Trusted Delivery](../../docs/trusted-delivery.md) owns delivery and storage contracts.

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
