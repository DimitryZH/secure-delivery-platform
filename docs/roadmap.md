# Roadmap

## Roadmap principle

The Secure Delivery Platform is organized around a trusted software delivery path.

The implementation sequence follows the release trust model: define release identity and trust boundaries first, establish the minimum executable foundation, enforce deployment trust, introduce controlled promotion, connect runtime evidence back to release decisions, and then turn those decision rules into executable platform controls.

The platform should remain focused on secure delivery rather than becoming a generic CI/CD framework, Terraform framework, Kubernetes platform, or broad SRE platform.

---

## Current implementation and validation boundaries

This roadmap describes architectural sequence and scope, not proof that every scenario below was executed. Canonical procedures and validation limits remain in [Trusted Delivery](trusted-delivery.md), [Observability](observability.md), and [Operator Runbook](operator-runbook.md).

- Implemented and live-validated: immutable trusted delivery and historical controlled promotion; structured logging, bounded health metrics, dashboard rendering, healthy-state availability alert inspection, and bounded release review. Read-only live validation for #80 produced a representative `READY / 0`, then a retention-driven `BLOCKED / 3` when source and rendered-artifact protection fell below the 75-minute margin. Both evaluations were read-only and performed no Cloud Deploy action. These observations do not authorize a future action or establish current eligibility.
- Implemented with offline-only coverage: other preflight outcomes and negative cases, review hold/reject scenarios, manual rejection/rollback workflow contracts, and rollback eligibility. No executed rollback or broader performance validation is claimed.
- Deferred: automated promotion/rollback, error/latency alerting, notification routing, SLOs, tracing, and broader performance validation. MVP tagging and GitHub Release publication require separate later authorization.

The preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize, or execute an action. Review, eligibility, action authorization, target approval, and execution remain separate boundaries; READY is eligibility only.

---

## Trusted Release Model

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

## Executable Foundation

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

## Trusted Delivery Path

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

## Controlled Promotion

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

## Operational Visibility

**Goal:** Connect runtime behavior to release identity and expose the operational evidence required for release decisions.

### Scope

* Cloud Monitoring visibility
* Cloud Logging visibility
* runtime release metadata correlation
* deployment health dashboard
* release-related log views and metrics
* alert policies for unhealthy rollout conditions

### Target outcome

Operators can determine:

* what source revision produced the running workload
* which build produced the artifact
* which immutable image digest is running
* whether verification and trust requirements were satisfied
* where the release is currently deployed
* whether runtime health provides sufficient evidence for the next release decision

Operational visibility supplies evidence. It does not itself authorize promotion, rejection, or rollback.

The delivery path becomes:

```text
Source
  → Build
  → Artifact
  → Verify
  → Trust
  → Deploy
  → Observe
```

---

## Platform Release Controls

**Goal:** Turn release decision rules into explicit, deterministic, and executable platform controls.

### Scope

* explicit release review checkpoint
* continue / hold / reject decision semantics
* manual release rejection workflow
* controlled rollback workflow
* rollback candidate eligibility rules
* executable promotion preflight
* executable rollback preflight
* deterministic READY / HOLD / BLOCKED outcomes
* machine-readable decision output
* fail-closed handling for missing or expired evidence
* separation of decision evaluation from deployment authorization and mutation

### Target outcome

The platform can evaluate whether a release action is currently eligible before Cloud Deploy performs the action.

A release decision evaluates evidence such as:

* release identity and immutable digest
* source, build, verification, and attestation correlation
* Binary Authorization compatibility
* source and rendered artifact availability
* retention protection margin
* target compatibility
* conflicting rollout state
* required caller authority
* required operational evidence

The resulting decision is explicit and reproducible:

```text
Fresh, Independently Reviewed, Operator-Supplied Snapshot
              +
Release + Target + Intended Action
              ↓
      Executable Preflight
              ↓
      READY / HOLD / BLOCKED
              ↓
     Separate Authorization
              ↓
       Cloud Deploy Action
```

A successful preflight does not perform promotion or rollback and does not replace environment approval gates. Mutation remains a separately authorized action.

This stage completes the core MVP platform capability: the system does not only execute a trusted delivery path; it also evaluates release eligibility using deterministic, fail-closed controls.

---

## MVP Release

**Goal:** Package the completed core platform as the first reproducible MVP release.

### Scope

* finalize canonical public documentation
* align architecture and roadmap with implemented behavior
* preserve existing historical controlled-promotion image references and sanitized validation conclusions; no new screenshots or raw evidence
* document the executable release decision flow
* verify repository links and public examples
* leave MVP tagging and GitHub Release publication to a separate later operator decision

### Target outcome

The documentation packaging target is a coherent end-to-end platform story; it does not claim completed tagging or publication. The implemented platform can:

* build and identify an immutable release candidate
* verify and attest that candidate
* enforce admission trust
* promote the same release across environments
* correlate runtime behavior with release identity
* evaluate release eligibility before promotion or rollback
* preserve separate authorization for deployment mutations

---

## Security and Operational Hardening

**Goal:** Strengthen the completed MVP and validate its behavior under broader failure conditions.

### Scope

* tighten IAM permissions and service account boundaries
* strengthen environment-specific trust policies
* improve verification failure handling
* improve Binary Authorization denial diagnostics
* validate release metadata consistency across the delivery path
* validate promotion failure and recovery behavior
* improve executable decision and rollback controls
* exercise representative failure scenarios
* remove unnecessary permissions and temporary implementation exceptions
* verify operational documentation against the implemented system

### Target outcome

The platform demonstrates a hardened, reproducible, and auditable trusted delivery path with clear behavior for both successful releases and security or operational failures.

---

## Completion criteria

The roadmap is complete when the platform can demonstrate that:

1. a source revision produces a uniquely traceable release candidate;
2. the resulting artifact is identified by immutable image digest;
3. verification determines whether the candidate can receive the required trust signal;
4. deployment policy prevents an untrusted artifact from running where trust enforcement is required;
5. the same trusted artifact progresses through `dev → stage → prod` without rebuild;
6. runtime workloads remain correlated with their release identity;
7. operational health is available as evidence for release decisions;
8. promotion and rollback eligibility can be evaluated by deterministic, executable, fail-closed preflight controls;
9. release decisions remain separate from approval and deployment mutation;
10. failed verification, denied deployment, blocked promotion, rejected release, blocked rollback, and unhealthy runtime conditions have explicit and diagnosable outcomes;
11. build, signing, deployment, review, and operational responsibilities remain separated by clear IAM and trust boundaries.
