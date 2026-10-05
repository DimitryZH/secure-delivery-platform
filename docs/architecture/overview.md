# Architecture Overview

## Component responsibilities

One project, one GKE cluster, three namespaces, and one service keep the platform small. Terraform manages infrastructure rather than orchestrating releases.

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

All namespaces share enforced admission. Dev has no Cloud Deploy approval requirement; stage/prod each require separate approval. Namespace routing does not establish strong RBAC isolation.

## Canonical contracts

- [Release Model](release-model.md): identity, metadata, trust boundaries, promotion.
- [Trusted Delivery](../trusted-delivery.md): executable mechanisms and protection limits.
- [IAM Model](../iam-model.md): authority scopes.
- [Operator Runbook](../operator-runbook.md): procedures/authorization gates.
- [Environment Policies](environment-policies.md): target differences.
- [MVP Boundaries](mvp-boundaries.md): intentional limits.
- [Diagrams](../diagrams/README.md): visual summaries.

Current validation uses readiness, digest, correlation, and internal HTTP checks. Application dashboards, alerts, automated rollback, and observability-driven promotion remain planned [Observability](../observability.md), following the architectural [Roadmap](../roadmap.md).
