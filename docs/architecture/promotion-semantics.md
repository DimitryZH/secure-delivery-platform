# Promotion Semantics

## Purpose

Promotion defines how a trusted release candidate moves between environments.

In this project, promotion is a governance action. It is not a rebuild, a retag operation, or an implicit side effect of a successful pipeline step.

## Promotion definition

Promotion means advancing the same identified release candidate from one environment to the next after the required trust and review conditions are satisfied.

A promoted release should preserve:
- commit SHA
- build ID
- build identity
- image repository
- image digest
- verification result
- trust signal reference, when available
- release metadata

If a new image digest is produced, the platform should treat it as a new release candidate that must re-enter the trust flow.

## Environment progression

The MVP progression path is:

```text
dev → stage → prod
```

Expected semantics:
- **dev** receives the initial controlled deployment candidate.
- **stage** receives only an explicitly promoted candidate from dev.
- **prod** receives only an explicitly promoted candidate from stage.

A successful deployment to one environment does not automatically authorize deployment to the next environment.

## Promotion gates

Promotion should be based on a small set of clear gates.

MVP gates:
- the release identity is complete enough for review
- the image digest is known and immutable
- required verification checks passed
- the required trust signal exists for the target environment
- the previous environment deployment completed successfully, when applicable
- operators have enough runtime visibility to make the promotion decision

For consistency, promotion checks should evaluate canonical metadata keys from the release contract (`commit_sha`, `build_id`, `image_digest`, `verification_status`, `trust_signal_ref`, `target_environment`, `promotion_state`).

## What promotion is not

Promotion is not:
- rebuilding the application
- changing the image digest
- retagging an unverified image to make it deployable
- bypassing Binary Authorization
- replacing operator review with pipeline success alone
- deploying directly to prod without a recorded environment progression

## MVP implementation expectation

For the MVP, promotion can remain operationally simple as long as the semantics are clear and demonstrable.

The first executable version should prove that:
- the same image digest moves through dev, stage, and prod
- deployment eligibility is checked before the target environment receives the release
- promotion is visible in release metadata or operator-facing records
- a blocked promotion or blocked deployment can be explained from trust state

## Deferred complexity

The MVP does not need complex change-control workflows, external change management integration, or custom release orchestration.

Those can be introduced later after the platform demonstrates a coherent trusted release path.
