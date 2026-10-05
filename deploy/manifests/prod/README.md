# Prod Deployment

This directory documents the `prod` target. Shared assets live in `../base/`; Cloud Deploy preparation produces the `prod` profile from the same digest-pinned candidate. Namespace, target annotation, and `APP_ENV` are `prod`; source/build/trust/digest identity is preserved.

Cloud Deploy requires separate approval for prod; promotion authorization alone does not approve deployment. Direct-consumer `--reviewed` is an operator assertion, not Cloud Deploy approval.

See [configuration/preparation](../../clouddeploy/README.md), [environment policies](../../../docs/architecture/environment-policies.md), and [Operator Runbook](../../../docs/operator-runbook.md).
