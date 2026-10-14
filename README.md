# Secure Delivery Platform

A Google-native delivery platform promoting one verified, attested image digest through dev, stage, and prod. Build, signing, and deployment authority remain separate.

```mermaid
flowchart TB
    Source[Source] --> Build[Cloud Build image execution]
    Build --> Registry[Artifact Registry digest]
    Registry --> Verify[Metadata verification]
    Verify --> Sign[Separate signer and KMS]
    Sign --> Deploy[Cloud Deploy: dev → stage → prod]
    Deploy --> Admission{Binary Authorization}
    Admission -->|trusted| Runtime[GKE target namespace]
    Admission -->|denied| Blocked[Pod admission blocked]
```

Cloud Deploy orchestrates existing trusted artifacts; Binary Authorization remains admission authority. Stage and prod require separate approval. Promotion never rebuilds, retags, or replaces the artifact.

The implemented path includes metadata verification, digest-bound attestation, enforced admission, protected source/render storage, and controlled promotion. Manual readiness and internal HTTP checks validate deployments. Implemented and live-validated: structured application logging in dev, request/latency ingestion for health traffic in dev, deployment availability signals, the deployment health dashboard, and the availability alert policy in its healthy non-firing state. Empty non-health traffic, error, and p95 panels are missing evidence, not performance validation or proof of zero errors.

## MVP implementation and validation

The preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize, or execute an action. Review, eligibility, action authorization, target approval, and execution remain separate boundaries; READY is eligibility only.

Read-only live validation for #80 produced a representative `READY / 0`, then a retention-driven `BLOCKED / 3` when source and rendered-artifact protection fell below the 75-minute margin. Both evaluations were read-only and performed no Cloud Deploy action. These observations do not authorize a future action or establish current eligibility.

Implemented with offline-only coverage: preflight HOLD and rollback eligibility scenarios, release review hold/reject scenarios, and manual rejection/rollback workflow contracts. No executed rollback is claimed.

Deferred: automated promotion and rollback, error/latency alerting, notification routing, SLOs, tracing, and broader performance validation. MVP tagging and GitHub Release publication require a separate operator decision; this documentation does not claim publication.

## Validated delivery path

Historical end-to-end controlled promotion was validated: the same verified and attested release progressed through `dev → stage → prod` without rebuilding or replacing the artifact. This is a validation snapshot, not a live infrastructure or status dashboard.

![The same trusted release deployed across dev, stage, and prod](docs/images/controlled-promotion/03-promotion-complete.png)

See [Controlled Promotion Validation](docs/trusted-delivery.md#controlled-promotion-validation) for the approval flow and the surrounding identity, trust, admission, and health checks.

## Repository structure

| Area | Responsibility |
| --- | --- |
| `app/` | Minimal sample service |
| `cloudbuild/` | Image, verification, and separate signing execution |
| `deploy/` | Shared manifests, consumer, and Cloud Deploy preparation |
| `terraform/` | Reproducible foundation |
| `monitoring/` | Implemented metric, dashboard, and availability alert definitions |
| `docs/` | Canonical architecture, contracts, and operations |

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Release Model](docs/architecture/release-model.md)
- [Trusted Delivery](docs/trusted-delivery.md)
- [Controlled Promotion Validation](docs/trusted-delivery.md#controlled-promotion-validation)
- [Environment Policies](docs/architecture/environment-policies.md)
- [IAM Model](docs/iam-model.md)
- [Operator Runbook](docs/operator-runbook.md)
- [MVP Boundaries](docs/architecture/mvp-boundaries.md)
- [Observability](docs/observability.md)
- [Architecture Diagrams](docs/diagrams/README.md)
- [Roadmap](docs/roadmap.md)

The architectural roadmap is not a deployment progress tracker. One project/cluster and three namespaces keep the MVP small; namespace routing is not strong IAM/RBAC isolation.
