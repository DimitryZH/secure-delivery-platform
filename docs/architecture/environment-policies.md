# Environment Policies

## Purpose

Environment policies define how release trust expectations change as a release moves from dev to stage to prod.

The MVP uses one GKE cluster with separate namespaces:
- dev
- stage
- prod

This keeps the platform reproducible while still demonstrating governed promotion and environment-specific trust.

## Environment policy summary

| Environment | Purpose | Trust posture | Promotion expectation |
| --- | --- | --- | --- |
| dev | First controlled deployment target | Relaxed enough for fast validation | Initial deployment after baseline checks |
| stage | Pre-production validation | Stricter trust and operator review | Explicit promotion from dev |
| prod | Controlled production target | Strictest MVP trust requirements | Explicit promotion after stage review |

## Verification expectations by environment

Verification requirements become stricter as a release moves toward prod. The MVP does not need separate verification systems per namespace; it needs clear expectations for how the same verification output is evaluated before promotion.

| Environment | Required verification expectation | Operator decision point |
| --- | --- | --- |
| dev | Required fields are present and baseline checks complete | Confirm the candidate is traceable before initial deployment |
| stage | `verification_status=passed`, immutable `image_digest`, and approved image location are confirmed | Review dev outcome before explicit promotion |
| prod | Stage expectations remain satisfied and the trust signal reference is reviewable | Allow promotion only after stage runtime review |

A failed verification result should stop promotion to stage or prod. Dev may be used to troubleshoot early failures, but it should not normalize bypassing release identity or artifact immutability.

Policy checks should evaluate canonical metadata keys (`commit_sha`, `build_id`, `image_digest`, `verification_status`, `trust_signal_ref`, `target_environment`) to keep environment decisions consistent with the release contract.

## Dev policy

Dev is the first controlled target in the release path.

Dev may intentionally relax some controls to keep feedback fast, but it should not bypass the platform model entirely.

MVP expectations for dev:
- image must come from the approved Artifact Registry repository
- image should be tied to a commit SHA and build ID
- basic build and verification checks should pass
- deployment should use the controlled release path when practical
- failures should be visible to operators

Intentionally relaxed in dev:
- a separate promotion gate may not be required
- Binary Authorization policy may be less strict while the trust path is being developed
- operational review may be lightweight

## Stage policy

Stage represents pre-production validation.

MVP expectations for stage:
- promotion from dev must be explicit
- release identity must include commit SHA, build ID, and image digest
- verification checks must pass before promotion
- Binary Authorization should enforce the required trust signal
- operators should review deployment and runtime health before prod promotion

Stage is where the project should demonstrate that promotion is a governed decision, not a side effect of a successful build.

## Prod policy

Prod has the strictest MVP trust expectations.

MVP expectations for prod:
- promotion from stage must be explicit
- deployment should require the verified image digest
- Binary Authorization should block artifacts without the required trust signal
- release metadata should be available for review
- operator review should happen before promotion
- rollback or recovery expectations should be documented before production-like demos

Prod should demonstrate controlled delivery without introducing unnecessary enterprise complexity.

## Production hardening expectations

The MVP should prepare for production hardening without implementing every advanced control immediately.

Expected later hardening areas:
- stronger promotion controls
- richer provenance
- stricter IAM separation
- additional Binary Authorization policies
- vulnerability policy integration
- audit-oriented release records
- environment-specific operational alerts

## Policy boundaries

Environment policies should stay focused on release trust and promotion semantics. They should not become a large Kubernetes platform design or a generic enterprise control framework.
