# Architecture Overview

## Component responsibilities

One project, one GKE cluster and three retained namespaces support the active Online Shop workload in dev. Sample-service is retired and has no recovery or preservation requirement. Terraform manages infrastructure rather than orchestrating releases.

| Component | Responsibility |
| --- | --- |
| Cloud Build image execution | Publish immutable image |
| Verification | Check candidate metadata against trusted settings |
| Separate signer and KMS | Recheck verification and sign digest |
| Artifact Registry | Store image bytes |
| Cloud Deploy | Render/orchestrate existing trusted release |
| Binary Authorization | Enforce attestation on new admission |
| GKE | Run namespaced workloads/ClusterIP Services |

```text
Source → Build → Artifact → Verification → Attestation → Cloud Deploy → Binary Authorization → GKE
```

All namespaces share enforced admission. The Online Shop dev target has no Cloud Deploy approval requirement; stage/prod promotion is future reviewed work. Namespace routing does not establish strong RBAC isolation.

## Canonical contracts

- [Release Model](release-model.md): identity, metadata, trust boundaries, promotion.
- [Trusted Delivery](../trusted-delivery.md): executable mechanisms and protection limits.
- [IAM Model](../iam-model.md): authority scopes.
- [Operator Runbook](../operator-runbook.md): procedures/authorization gates.
- [Environment Policies](environment-policies.md): target differences.
- [MVP Boundaries](mvp-boundaries.md): intentional limits.
- [Diagrams](../diagrams/README.md): visual summaries.

Historical sample-service validation only: structured application logging in dev, request/latency ingestion for health traffic in dev, deployment availability signals, the deployment health dashboard, and the availability alert policy in its healthy non-firing state. Empty non-health traffic, error, and p95 panels are missing evidence, not performance validation or proof of zero errors. See [Observability](../observability.md) for validation limits.

The preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize, or execute an action. Review, eligibility, action authorization, target approval, and execution remain separate boundaries; READY is eligibility only. Representative promotion READY and retention-driven BLOCKED outcomes were live-validated read-only; other decision and rollback scenarios have offline-only coverage. See [Operator Runbook](../operator-runbook.md#release-decision-preflight).

Automated promotion/rollback, error/latency alerting, notification routing, SLOs, tracing, and broader performance validation remain deferred in the [Roadmap](../roadmap.md).
