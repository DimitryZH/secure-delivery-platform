# IAM Model

## Authority matrix

Configured responsibilities are distinct. Effective access also depends on inherited/group grants and privileged submitters.

| Identity | Authority / scope | Boundary |
| --- | --- | --- |
| `<BUILD_SERVICE_ACCOUNT>` | Artifact Registry writer, Cloud Build builder, log writer | No direct signer/deploy/impersonation grant |
| `<ATTESTATION_SERVICE_ACCOUNT>` | One KMS key signer/verifier; one attestor reader/verifier; one note attachment/viewing; custom project occurrence create/get/list; log writer; dedicated source-bucket viewer | No image writer, deploy, policy administration, or build-creation role |
| `<DEPLOY_SERVICE_ACCOUNT>` | Cloud Deploy Job Runner, container developer, log writer | Cluster access is broader than namespace routing |
| Node identity | Logging/metrics plus separately granted repository reader | Image pull is separate authority |
| Reviewer | Logging/Monitoring viewer baseline | Occurrence/attestor inspection access needs separate review |
| Provisioning operator | Reviewed infrastructure management | Plan/apply authority is separate from rollout authority |
| Release caller/promoter/approver | Specific Cloud Deploy operation permissions and execution-account `actAs` | No automatic authority from build success or Token Creator |

Same-project Google-managed Cloud Deploy, Cloud Build, and Binary Authorization agents require their matching service-agent roles. Grant such roles only to the matching Google-managed principal represented by `<PROJECT_NUMBER>`, never ordinary execution accounts/operators. Verify service identity existence and unconditional project bindings; API enablement alone does not prove prerequisites.

## Operator access

A non-authoritative deploy-account IAM member grants `roles/iam.serviceAccountTokenCreator` to sensitive required `deployment_operator_principal`. Only specific `user:` or `group:` inputs are accepted, not service accounts, public principals, empty values, or a hardcoded operator. No builder delegation is added.

Supply the actual member privately for required Terraform operations. Never commit it in tfvars/docs/comments. Token Creator permits short-lived credentials/signing as deploy authority; it is not release creation, promotion, approval, or `actAs`. Inspect caller operation permissions and `iam.serviceAccounts.actAs` on execution authority separately. Do not add broad IAM to make an operation pass.

## Storage and isolation limits

Cloud Build builder and Cloud Deploy Job Runner include inherited project storage access; bucket IAM cannot subtract it. Prefixes are not IAM boundaries. Unlocked retention protects bytes but is administratively mutable. Namespace routing does not narrow existing container permissions.

Absence of direct build grants does not prove absence of organization/group inheritance, privileged trigger access, or arbitrary code as the signer. Review those paths explicitly; never make signing build-controlled. Cross-project resources require separate permission review.

## Credential and plan safety

Public examples use `<PROJECT_ID>`, `<PROJECT_NUMBER>`, `<BUILD_SERVICE_ACCOUNT>`, `<DEPLOY_SERVICE_ACCOUNT>`, and `<ATTESTATION_SERVICE_ACCOUNT>`. Replace privately; no operational identity is renamed.

`sensitive=true` redacts ordinary Terraform display, not state, binary/JSON plans, refresh IDs, or logs. Keep backend config, private tfvars, raw evidence, tokens, and credentials private/ignored. Redact provider output before sharing. The existing backend is `<TF_STATE_BUCKET>` with `secure-delivery-platform/foundation`; documentation maintenance never migrates state.

See [Trusted Delivery](trusted-delivery.md) for execution isolation and [Operator Runbook](operator-runbook.md) for authorization gates.
