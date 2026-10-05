# MVP Boundaries

## Scope

One sample service, one project, one zonal cluster, and dev/stage/prod namespaces demonstrate trusted delivery. Artifact Registry, Cloud Build, a separate KMS-backed attestor, Binary Authorization, Cloud Deploy, and explicit Terraform resources form the foundation.

Each deployed namespace has the sample Deployment and ClusterIP Service. Minimal environment settings and readiness/internal HTTP validation suffice. External LoadBalancer/Ingress is unnecessary.

## Deliberate limits

A shared cluster reduces cost but does not strongly isolate environments. Admission is uniform; namespace routing is not RBAC. One attestor certifies a narrow metadata gate, not full provenance. Storage retention is unlocked with finite lifetime.

Prefer readable explicit resources/IAM and the existing backend. Avoid premature modules, deep overlays, excessive indirection, and enterprise frameworks. [Terraform Foundation](../../terraform/foundation/README.md) supplies directory guidance; [IAM Model](../iam-model.md) owns canonical authority boundaries.

## Deferred and excluded scope

Multi-cluster, multiple services/attestors, advanced vulnerability policy, complex GitOps, automated rollback, custom catalogs, enterprise change control, and organization policy are deferred. Multi-cloud, service mesh, generic developer-platform frameworks, non-Google targets, and custom orchestrators are outside MVP.

Logging/Monitoring access exists; application dashboards/alerts/release metrics and observability-driven promotion remain planned [Observability](../observability.md). Manual checks do not imply those features exist.

## Demonstration criteria

Demonstrate source/build/digest identity, verification rejection, separate signed trust, admission enforcement, approval-controlled progression, and correlated runtime health. Live negative admission tests need separate authorization; trusted success alone does not prove them. [Operator Runbook](../operator-runbook.md) defines scenario boundaries without tracking progress.
