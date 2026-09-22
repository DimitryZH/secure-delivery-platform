# Secure Delivery Platform

Secure Delivery Platform defines and incrementally implements a trusted software delivery path for containerized workloads on Google Cloud.

The platform is organized around a release candidate whose identity remains traceable from source through runtime. Build success alone does not make an artifact deployable: verification, trust policy, environment policy, and runtime evidence all contribute to release decisions.

```text
Source → Build → Artifact → Verify → Trust → Deploy → Observe → Promote
```

## Architecture

The MVP uses Google Cloud services with deliberately narrow responsibilities:

- **Cloud Build** builds and verifies release candidates and records release metadata.
- **Artifact Registry** stores container images identified by immutable digest.
- **Binary Authorization** represents the deployment admission boundary.
- **Cloud Deploy** provides explicit progression through target environments.
- **GKE** runs the workload in separate `dev`, `stage`, and `prod` namespaces.
- **Cloud Monitoring and Cloud Logging** provide evidence for post-deployment review and promotion decisions.

The Trusted Release Model is documented. The executable foundation and later enforcement, promotion, and operational capabilities are delivered through the roadmap milestones; documentation of a component does not imply that it is already deployed.

See the [Architecture Overview](docs/architecture/overview.md) and [Architecture Diagrams](docs/diagrams/README.md) for the complete design.

## Trusted release principles

- A release candidate has a canonical identity spanning source, build, artifact, verification, promotion, and runtime.
- The immutable image digest is the artifact identity used by verification and deployment controls.
- Build and deployment authority remain separate trust boundaries.
- Promotion advances the same release candidate; it does not rebuild or replace the artifact.
- Environment policy becomes stricter from `dev` through `stage` to `prod`.
- Runtime evidence informs the explicit release decision for further promotion.

## Repository structure

| Area | Responsibility |
| --- | --- |
| `app/` | Minimal sample workload used to exercise the delivery path |
| `cloudbuild/` | Build and verification configuration |
| `deploy/` | Kubernetes manifests and Cloud Deploy assets |
| `docs/` | Architecture, policy, operations, diagrams, and the canonical roadmap |
| `monitoring/` | Dashboard, log-based metric, and alert policy assets |
| `terraform/` | Reproducible Google Cloud and GKE foundation |

## Documentation

- [Architecture Overview](docs/architecture/overview.md)
- [Trusted Release Model](docs/architecture/trust-model.md)
- [Release Identity](docs/architecture/release-identity.md)
- [Release Metadata Contract](docs/architecture/release-metadata.md)
- [Promotion Semantics](docs/architecture/promotion-semantics.md)
- [Environment Policies](docs/architecture/environment-policies.md)
- [MVP Boundaries](docs/architecture/mvp-boundaries.md)
- [Release Flow](docs/release-flow.md)
- [Architecture Diagrams](docs/diagrams/README.md)
- [Security Controls](docs/security-controls.md)
- [Cloud Build Verification](docs/cloudbuild-verification.md)
- [Binary Authorization](docs/binary-authorization.md)
- [Observability](docs/observability.md)
- [Operator Runbook](docs/operator-runbook.md)
- [Roadmap](docs/roadmap.md)

## Roadmap

The canonical roadmap is maintained in [docs/roadmap.md](docs/roadmap.md):

1. **Trusted Release Model**
2. **Executable Foundation**
3. **Trusted Delivery Path**
4. **Controlled Promotion**
5. **Operational Visibility**
6. **Security and Operational Hardening**

Implementation builds on the same release identity and trust boundaries, adding executable behavior without redefining the Trusted Release Model.
