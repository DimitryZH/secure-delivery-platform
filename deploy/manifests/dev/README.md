# Dev Deployment

This directory documents the `dev` target. Shared assets live in `../base/`; Cloud Deploy preparation produces the `dev` profile from the same digest-pinned candidate. Namespace, target annotation, and `APP_ENV` are `dev`; source/build/trust/digest identity is preserved.

The initial dev rollout is explicitly authorized and has no Cloud Deploy approval requirement. Direct-consumer `--reviewed` is an operator assertion, not Cloud Deploy approval.

See [configuration/preparation](../../clouddeploy/README.md), [environment policies](../../../docs/architecture/environment-policies.md), and [Operator Runbook](../../../docs/operator-runbook.md).
