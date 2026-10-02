# Deployment operator impersonation

Related to #52. The operator needs a short-lived token for the separate
deployment identity before the existing CLI can execute. Terraform adds one
non-authoritative `google_service_account_iam_member.deployment_operator`:

- Role: `roles/iam.serviceAccountTokenCreator`.
- Resource: `google_service_account.deploy.name` only, never the project.
- Member: sensitive required variable `deployment_operator_principal`.

The variable accepts specific `user:` or `group:` members, not service accounts,
public principals, empty values or a hardcoded operator. Build authority gets
no delegation grant. Supply the value privately for every subsequent plan/apply
that requires it; do not add it to committed tfvars, documentation or comments.

PowerShell example (replace the placeholder only in the local session):

```powershell
$env:TF_VAR_deployment_operator_principal = 'user:<operator-email>'
terraform -chdir=terraform/foundation plan -input=false -lock=true -lock-timeout=60s -no-color -out=issue52-20261002-deployment-operator-locked.tfplan
Remove-Item Env:TF_VAR_deployment_operator_principal
```

Public docs and comments use variables or display-only masked identifiers such
as `secure-delivery-deploy@sre-platform-staging-***.iam.gserviceaccount.com`.
Do not pass masked strings to APIs. Operational Terraform resource references
and executable deployment configuration must remain valid; no operational
identity is renamed. Public example metadata uses placeholders, materialized
locally when needed.

`sensitive = true` redacts the operator member from normal plan output. Terraform
state and binary/JSON plans still contain the actual value. Keep them private:
the saved plan and full evidence remain in ignored local paths, not the PR.
Future provider refresh IDs and logs can also contain the principal; redact
them before sharing publicly, even with a sensitive input variable.
The role permits short-lived token creation and signing as the deployment
identity; only a reviewed operator should receive it. The account's existing
deployment permissions determine what those credentials can do.

This preparation performs no apply, API enablement, workload deployment, or
other IAM mutation. Live Issue #52 deployment and build-to-deploy denial tests
remain separate authorized validation steps after access is provisioned.
