# MVP Boundaries

## Purpose

This document defines the complexity boundaries for the first working version of the platform.

The MVP should prove the trusted release model before expanding into broader platform engineering concerns.

## MVP scope

The MVP includes:
- a single sample service
- one Google Cloud project baseline, unless a demo requires otherwise
- one GKE cluster
- three namespaces: dev, stage, and prod
- Artifact Registry for container images
- Cloud Build for build and verification execution
- Binary Authorization for deployment trust enforcement
- Cloud Deploy for controlled promotion
- Terraform for a clear, reproducible foundation
- Cloud Monitoring and Cloud Logging for release visibility
- runnable demo scenarios that show the trusted path

## Intentionally deferred

The following areas are deferred until the trusted release path is coherent and executable:
- multi-cluster topology
- advanced Kubernetes overlays
- complex GitOps workflows
- multiple services
- multiple attestors
- advanced vulnerability management policy
- custom release catalog or metadata database
- enterprise change-control workflows
- organization-wide policy hierarchy
- sophisticated rollback automation

## Explicitly out of scope for MVP

The MVP explicitly does not include:
- multi-cloud support
- service mesh
- generic internal developer platform abstractions
- a reusable Terraform framework
- broad enterprise platform modules
- complex multi-tenant cluster design
- custom CI/CD orchestrators outside Google-native services
- non-Google deployment targets

## Single cluster approach

The MVP uses a single GKE cluster with separate namespaces for dev, stage, and prod.

This approach is intentional because it:
- keeps the baseline reproducible
- reduces infrastructure cost and setup complexity
- keeps attention on release trust rather than cluster topology
- still allows environment-specific promotion and policy demonstrations

A future version may introduce separate clusters if the project needs stronger environment isolation, but that is not required to prove the delivery model.

## Google-native scope

The project remains Google-native for the MVP.

Primary services:
- Cloud Build
- Artifact Registry
- Binary Authorization
- Cloud Deploy
- GKE
- Cloud Monitoring
- Cloud Logging
- Terraform with the Google provider

The goal is to demonstrate how these services form a governed release system, not to create a generic multi-provider framework.

## Terraform boundary

Terraform should provide a clear and reproducible platform baseline.

Terraform should not become the platform product itself.

MVP Terraform should prioritize:
- readability
- minimal required resources
- explicit service accounts and IAM
- reproducible setup
- low abstraction
- a foundation inventory aligned with the trusted release path

The foundation inventory is defined in [Terraform Foundation](../../terraform/foundation/README.md).

Avoid in the MVP:
- premature module extraction
- deeply nested module hierarchies
- enterprise-style framework patterns
- excessive variable indirection

## Kubernetes boundary

The Kubernetes design should stay intentionally simple.

MVP Kubernetes should include:
- one Deployment
- one Service
- dev, stage, and prod namespaces
- minimal environment-specific configuration
- health checks suitable for deployment validation

Avoid in the MVP:
- service mesh
- advanced ingress architecture
- complex network policy design
- multi-cluster deployment patterns
- heavy overlay systems unless required by Cloud Deploy rendering

## Success criteria

The MVP is successful when it can demonstrate:
- a release identity tied to source, build, and image digest
- a verification step that affects deployment eligibility
- a trusted artifact being deployed
- an untrusted artifact being blocked
- explicit promotion from dev to stage to prod
- operator visibility tied to the release identity

The MVP does not need to look like a full enterprise platform. It needs to prove that governed release trust works end to end.
