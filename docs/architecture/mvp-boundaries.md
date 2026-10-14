# MVP Boundaries

## Scope

One sample service, one project, one zonal cluster, and dev/stage/prod namespaces demonstrate trusted delivery. Artifact Registry, Cloud Build, a separate KMS-backed attestor, Binary Authorization, Cloud Deploy, and explicit Terraform resources form the foundation.

Each deployed namespace has the sample Deployment and ClusterIP Service. Minimal environment settings and readiness/internal HTTP validation suffice. External LoadBalancer/Ingress is unnecessary.

## Deliberate limits

A shared cluster reduces cost but does not strongly isolate environments. Admission is uniform; namespace routing is not RBAC. One attestor certifies a narrow metadata gate, not full provenance. Storage retention is unlocked with finite lifetime.

Prefer readable explicit resources/IAM and the existing backend. Avoid premature modules, deep overlays, excessive indirection, and enterprise frameworks. [Terraform Foundation](../../terraform/foundation/README.md) supplies directory guidance; [IAM Model](../iam-model.md) owns canonical authority boundaries.

## Deferred and excluded scope

Multi-cluster, multiple services/attestors, advanced vulnerability policy, complex GitOps, automated rollback, custom catalogs, enterprise change control, and organization policy are deferred. Multi-cloud, service mesh, generic developer-platform frameworks, non-Google targets, and custom orchestrators are outside MVP.

Implemented and live-validated: structured application logging in dev, request/latency ingestion for health traffic in dev, deployment availability signals, the deployment health dashboard, and the availability alert policy in its healthy non-firing state. Empty non-health traffic, error, and p95 panels are missing evidence, not performance validation or proof of zero errors. Metrics correlate to release identity through independent runtime review; they are not a release database. See [Observability](../observability.md).

Implemented with offline-only coverage: review hold/reject and manual rejection/rollback contracts, including rollback preflight eligibility. Representative promotion READY and retention-driven BLOCKED were live-validated read-only; rollback execution was not validated.

Automated promotion/rollback, error/latency alerting, notification routing, SLOs, tracing, and broader performance validation remain deferred. Tagging and GitHub Release publication are separate later decisions.

## Demonstration criteria

Demonstrate source/build/digest identity, verification rejection, separate signed trust, admission enforcement, approval-controlled progression, and correlated runtime health. Live negative admission tests need separate authorization; trusted success alone does not prove them. [Operator Runbook](../operator-runbook.md) defines scenario boundaries without tracking progress.
