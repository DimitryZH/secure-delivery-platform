# Architecture Overview

## Goal

The platform demonstrates a governed release path for containerized workloads on Google Cloud.

It is not centered on a single CI job. Instead, it is designed as a delivery system made of several coordinated control points:

- build
- verification
- artifact storage
- release promotion
- deployment trust enforcement
- post-deployment observability

## Architectural principles

### 1. Trusted release over simple automation

A release should not move forward only because a script completed successfully. It should move forward because it satisfies defined trust conditions.

The architecture is therefore organized around release identity, trust signals, deploy eligibility, and explicit promotion.

### 2. Separation of responsibilities

Different layers have different roles:

- **Cloud Build** builds, verifies, and records release metadata
- **Artifact Registry** stores immutable container artifacts
- **Binary Authorization** enforces deployment trust
- **Cloud Deploy** controls promotion across environments
- **GKE** runs the workload
- **Cloud Monitoring / Logging** provide runtime visibility

### 3. Promotion is explicit

Moving from one environment to another is treated as a controlled release action.

Promotion should move a known release identity, not an ambiguous image tag or an uncontrolled deployment state.

### 4. Operators need visibility

Release trust does not end at image creation. The platform includes runtime visibility so operators can assess release health and decide whether promotion should continue.

## Reference flow

```text
Source change
   ↓
Cloud Build validates and builds
   ↓
Artifact pushed to Artifact Registry
   ↓
Release identity and image digest recorded
   ↓
Verification produces a trust signal
   ↓
Binary Authorization policy determines deploy eligibility
   ↓
Cloud Deploy promotes release through environments
   ↓
GKE receives policy-eligible release
   ↓
Cloud Monitoring / Logging expose release health
```

## Environment model

MVP baseline:
- **dev** — initial controlled target with intentionally relaxed feedback-oriented controls
- **stage** — pre-production validation target with stricter trust expectations
- **prod** — controlled production target with the strictest MVP trust expectations

The MVP uses one GKE cluster with separate namespaces for dev, stage, and prod. This keeps the platform reproducible while still demonstrating environment-specific trust and promotion governance.

## Core architecture documents

- [Release Identity](release-identity.md)
- [Release Metadata Contract](release-metadata.md)
- [Trust Model](trust-model.md)
- [Promotion Semantics](promotion-semantics.md)
- [Environment Policies](environment-policies.md)
- [MVP Boundaries](mvp-boundaries.md)
- [Architecture Diagrams](../diagrams/README.md)

## Why this is a platform

A platform coordinates multiple components and establishes operating rules across the full release path.

This project qualifies as a platform because it defines:
- a repeatable delivery model
- a governed trust boundary for releases
- release identity and deploy eligibility expectations
- promotion rules across environments
- operator review and runtime visibility
- reusable structure rather than a one-off deployment script

## What this project is not

This repository is not:
- just a single YAML pipeline
- just a sample build trigger
- just a Kubernetes deployment example
- just a security scanning demo
- a generic Terraform framework
- a multi-cloud platform
- an advanced Kubernetes architecture project

It is a structured release system with multiple control points and an intentionally bounded MVP scope.
