# Environment Policies

## Shared enforcement

All targets require complete verified metadata, exact digest, current attestation, and separate authorized deployment identity. One cluster enforces the same Binary Authorization attestor rule across dev/stage/prod. Dev is not an unsigned-artifact sandbox.

| Target | Namespace / APP_ENV | Cloud Deploy approval | Progression |
| --- | --- | --- | --- |
| dev | dev | false | Explicit initial rollout authorization |
| stage | stage | true | Review dev; separately authorize promotion and approval |
| prod | prod | true | Review stage; separately authorize promotion and approval |

The pipeline orders dev → stage → prod. Inspect live target and release snapshot settings; updating a target does not redefine an existing release snapshot.

## Identity and stop conditions

Keep source/build/verification/trust/digest fixed. Namespace, environment annotation, and `APP_ENV` vary. Profiles select namespaces, not scoped IAM/RBAC. Direct `--reviewed` is not Cloud Deploy approval.

Stop on failed prior rollout, unavailable artifact/attestation, hash mismatch, insufficient protection, changed IAM/admission, or unexpected replacement. No rebuild/retag, bypass, automatic expired-release recreation, or corrective mutation without authorization.

Runtime review currently means rollout/readiness/digest/correlation/internal HTTP checks. Metric/alert-driven gates remain planned. See [Release Model](release-model.md), [Trusted Delivery](../trusted-delivery.md), and [Operator Runbook](../operator-runbook.md).
