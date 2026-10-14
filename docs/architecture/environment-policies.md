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

Runtime review combines rollout/readiness/digest/correlation/internal HTTP checks with implemented logs, metrics, dashboard, and availability alert inspection. Live validation covers the bounded availability baseline, not application performance or a real firing incident. Automatic metric/alert-driven promotion and rollback remain deferred.

The preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize, or execute an action. Review, eligibility, action authorization, target approval, and execution remain separate boundaries; READY is eligibility only. Promotion READY and retention-driven BLOCKED were live-validated read-only; rollback eligibility and other decision scenarios have offline-only coverage. See [Release Model](release-model.md), [Trusted Delivery](../trusted-delivery.md), and [Operator Runbook](../operator-runbook.md).
