# Release Flow

## Objective

Define the path a release takes from source change to deployed workload in GKE.

The release flow is governed by release identity and trust signals. A build result becomes deployable only when the platform can identify the artifact, verify it, and evaluate its eligibility for the target environment.

## Flow summary

1. A source change triggers the build workflow.
2. Cloud Build performs validation and image build tasks.
3. The container image is stored in Artifact Registry.
4. The release identity is recorded using commit SHA, build ID, build identity, image URI, and image digest.
5. Verification checks run against the release candidate.
6. Successful verification creates or prepares the trust signal for deployment enforcement.
7. Binary Authorization evaluates deploy eligibility for the target environment.
8. Cloud Deploy handles explicit promotion through target environments.
9. Policy-eligible releases are deployed to GKE.
10. Operators run a post-deployment review loop using dashboards, log-based metrics, and alert policies.
11. Promotion continues only when runtime review confirms release health and release identity alignment.

## Logical stages

### Stage 1 — Build and pre-release verification

This stage validates that the application is fit to become a release candidate.

Typical checks:
- linting
- tests
- build success
- selected security checks
- image creation
- image digest capture
- release metadata creation

### Stage 2 — Artifact registration

The built image is pushed to Artifact Registry and becomes a candidate artifact for deployment.

The artifact should be identified by immutable image digest before it is treated as a trusted release candidate.

### Stage 3 — Release trust

Binary Authorization and related trust rules determine whether the artifact may be deployed.

Build success is not enough. The release must satisfy the trust model and the policy expectations of the target environment.

### Stage 4 — Promotion

Cloud Deploy manages release progression:
- dev
- stage
- prod

Promotion is explicit. A release that reaches dev does not automatically become eligible for stage or prod.

### Stage 5 — Runtime review

After deployment, operators review runtime signals before approving further promotion.

Runtime review should be tied back to release identity so operators can answer what was deployed, where it was deployed, and whether it is healthy.

The MVP runtime review loop should combine:
- dashboards for deployment health, error rate, latency, and release metadata lookup
- log-based metrics for release events, denials, and error bursts
- alert policies for unhealthy rollout conditions

### Stage 6 — Promotion decision checkpoint

Promotion is allowed to continue only when runtime review confirms:
- the running workload still maps to the intended commit SHA, build ID, and image digest
- verification and trust expectations remain satisfied for the next environment
- no blocking runtime health signal requires rollback or investigation

If any checkpoint condition is not met, the release path should pause in the current environment until operators complete investigation and record a clear decision to continue, rollback, or reject the release candidate.

## Design intent

The key design decision is that deployment should be the result of a trusted release decision, not the default outcome of a successful build.

Related architecture documents:
- [Release Identity](architecture/release-identity.md)
- [Cloud Build Verification Expectations](cloudbuild-verification.md)
- [Trust Model](architecture/trust-model.md)
- [Environment Policies](architecture/environment-policies.md)
- [Operator Runbook](operator-runbook.md)
- [Observability](observability.md)
