# Trust Model

## Purpose

The platform is organized around trusted software delivery, not around tooling alone.

The trust model defines how a source change becomes a deployable release and where the platform enforces release eligibility.

## Trusted release definition

A trusted release is a release candidate that satisfies the platform's minimum trust conditions for a target environment.

For the MVP, a release is trusted when:
- it was built by the expected Cloud Build path
- it was produced by the expected build identity
- it is stored in the approved Artifact Registry repository
- it has an immutable image digest
- it passed the required verification checks
- it has a trust signal that can be evaluated before deployment
- it is promoted through the expected environment path

## Verification to deploy eligibility flow

The intended flow is:

```text
Source change
  → Cloud Build creates release candidate
  → Verification checks run against the candidate
  → Successful verification creates a trust signal
  → Binary Authorization evaluates deploy eligibility
  → Cloud Deploy promotes the trusted release
  → GKE admits only releases that satisfy policy
```

The key rule is that build success is necessary but not sufficient. Deployment eligibility depends on the trust signal and the target environment policy.

Minimum machine-readable gate criteria should align to canonical metadata keys:
- `commit_sha`
- `build_id`
- `image_digest`
- `verification_status`
- `trust_signal_ref`, when required by environment policy

## Promotion semantics

Promotion means moving the same identified release candidate from one environment to the next after the required trust and review conditions are satisfied.

Promotion does not mean rebuilding the application, retagging an image, or bypassing environment policy. If a new image digest is produced, it is a new release candidate and should re-enter the trust flow.

MVP promotion rules:
- dev receives the initial controlled deployment candidate
- stage receives only an explicitly promoted candidate from dev
- prod receives only an explicitly promoted candidate from stage
- each promotion should preserve the release identity and image digest
- operators should be able to see the current promotion state

## Role of Cloud Build

Cloud Build is the controlled build and verification execution layer.

In the MVP, Cloud Build should:
- build the container image
- publish it to the approved Artifact Registry repository
- resolve and record the image digest
- run minimal verification checks
- emit release metadata
- create or prepare the minimal trust signal used by deployment enforcement

Cloud Build should not become an unrestricted deployment identity. Its role is to produce and verify release candidates, not to bypass promotion or admission controls.

## Role of Binary Authorization

Binary Authorization is the deployment trust enforcement layer.

Its role is to answer whether an image is eligible to run in a target GKE environment based on policy and trust signals.

In the MVP, Binary Authorization should support:
- a blocked deployment scenario for an untrusted artifact
- a successful deployment scenario for a verified artifact
- different expectations for dev, stage, and prod
- operator troubleshooting when deployment is denied

## Minimal attestation model for MVP

The MVP should use a deliberately small attestation model.

Minimum model:
- one logical attestor representing the platform verification gate
- one verification path that can produce the required trust signal
- an image digest as the attested subject
- environment policies that decide where attestation is required

The MVP does not need multiple attestors, complex multi-attestor policy chains, or a full enterprise provenance framework. Those can be added after the trusted path is executable and understandable.

## Trust boundaries

The platform has the following trust boundaries:

### Source to build

Only expected source changes should trigger the controlled build path.

### Build to artifact

Only the build identity should publish release candidate artifacts to the approved repository path.

### Artifact to trust signal

Only verified image digests should receive a trust signal.

### Trust signal to deployment

Only artifacts that satisfy target environment policy should be deployable.

### Deployment to promotion

A successful deployment to one environment does not automatically prove readiness for the next environment. Promotion remains an explicit governance action.

### Runtime to release review

Runtime health is not a substitute for pre-deployment trust, but it is required for safe promotion decisions.

## Intentional constraints

The first implementation should keep the trust model narrow and auditable. The goal is to make the release path coherent before adding more tools, policies, or infrastructure complexity.
