# Roadmap

## Roadmap principle

The Secure Delivery Platform is organized around a trusted software delivery path.

The implementation sequence follows the release trust model: define release identity and trust boundaries first, establish the minimum executable foundation, enforce deployment trust, introduce controlled promotion, and connect runtime evidence back to release decisions.

The platform should remain focused on secure delivery rather than becoming a generic CI/CD framework, Terraform framework, or Kubernetes platform.

---

## Milestone 1 — Trusted Release Model

**Goal:** Define the governance and trust model before expanding the implementation.

### Scope

* define release identity
* define the release metadata contract
* define the trust model and trust boundaries
* define promotion semantics
* define environment-specific policies
* define MVP boundaries
* establish canonical metadata fields used by verification and promotion controls

### Target outcome

The platform has a coherent definition of what constitutes a release candidate, what makes an artifact trusted, and what conditions make it eligible for deployment to each environment.

---

## Milestone 2 — Executable Foundation

**Goal:** Establish the minimum infrastructure and delivery components required to execute the trusted release path.

### Scope

* Terraform foundation
* Artifact Registry
* initial GKE environment
* build and deployment service identities
* least-privilege IAM baseline
* sample workload
* Cloud Build trigger and build path
* container image publication
* immutable image digest capture
* initial machine-readable release metadata

### Target outcome

A source change can produce a traceable container artifact in the approved registry, with its source revision, build identity, build execution, and immutable image digest recorded.

---

## Milestone 3 — Trusted Delivery Path

**Goal:** Make release verification and deployment trust enforceable.

### Scope

* executable Cloud Build verification
* release metadata validation
* approved artifact location validation
* immutable digest validation
* verification result generation
* minimal trust signal / attestation path
* Binary Authorization configuration
* environment-aware deployment policy
* trusted deployment scenario
* blocked untrusted deployment scenario
* separation of build and deployment authority

### Target outcome

Build success alone is insufficient for deployment. Only a release candidate that satisfies the required verification and trust conditions can pass the deployment admission boundary.

---

## Milestone 4 — Controlled Promotion

**Goal:** Introduce explicit environment progression without rebuilding or changing the trusted artifact.

### Scope

* Cloud Deploy delivery pipeline
* dev → stage → prod progression
* digest-pinned deployment
* preservation of release identity across environments
* environment-specific promotion gates
* promotion state tracking
* deployment result recording
* blocked promotion behavior

### Target outcome

The same verified image digest can progress through the environment sequence while preserving its release identity and satisfying the policy requirements of each target environment.

Promotion does not rebuild, retag, or replace the release candidate.

---

## Milestone 5 — Operational Visibility

**Goal:** Connect runtime behavior to release identity and use operational evidence as part of release progression.

### Scope

* Cloud Monitoring visibility
* Cloud Logging visibility
* runtime release metadata correlation
* deployment health dashboard
* release-related log views and metrics
* alert policies for unhealthy rollout conditions
* operator review workflow
* promotion decision checkpoint
* rollback and release rejection workflow

### Target outcome

Operators can determine:

* what source revision produced the running workload
* which build produced the artifact
* which immutable image digest is running
* whether verification and trust requirements were satisfied
* where the release is currently deployed
* whether runtime health supports further promotion

The complete path becomes:

```text
Source
  → Build
  → Artifact
  → Verify
  → Trust
  → Deploy
  → Observe
  → Promote
```

---

## Milestone 6 — Security and Operational Hardening

**Goal:** Strengthen the completed trusted release path and validate its behavior under failure conditions.

### Scope

* tighten IAM permissions and service account boundaries
* strengthen environment-specific trust policies
* improve verification failure handling
* improve Binary Authorization denial diagnostics
* validate release metadata consistency across the delivery path
* validate promotion failure and recovery behavior
* improve runtime review and rollback procedures
* exercise representative failure scenarios
* remove unnecessary permissions and temporary implementation exceptions
* verify operational documentation against the implemented system

### Target outcome

The platform demonstrates a complete, reproducible, and auditable trusted delivery path with clear behavior for both successful releases and security or operational failures.

---

## Completion criteria

The roadmap is complete when the platform can demonstrate that:

1. a source revision produces a uniquely traceable release candidate;
2. the resulting artifact is identified by immutable image digest;
3. verification determines whether the candidate can receive the required trust signal;
4. deployment policy prevents an untrusted artifact from running where trust enforcement is required;
5. the same trusted artifact progresses through `dev → stage → prod` without rebuild;
6. runtime workloads remain correlated with their release identity;
7. operational health is evaluated before further promotion;
8. failed verification, denied deployment, failed promotion, and unhealthy runtime conditions have explicit and diagnosable outcomes;
9. build, deployment, and operational responsibilities remain separated by clear IAM and trust boundaries.
