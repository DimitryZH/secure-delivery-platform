# Roadmap

## Roadmap principle

The Secure Delivery Platform is organized around a trusted software delivery path.

The implementation sequence follows the release trust model: define release identity and trust boundaries first, establish the minimum executable foundation, enforce deployment trust, introduce controlled promotion, connect runtime evidence back to release decisions, and turn those decision rules into executable platform controls. After the first MVP release, integrate Online Shop as a representative application workload, then strengthen security and operational resilience.

The platform should remain focused on secure delivery rather than becoming a generic CI/CD framework, Terraform framework, Kubernetes platform, or broad SRE platform.

---

## Current implementation and validation boundaries

This roadmap describes architectural sequence and scope, not proof that every scenario below was executed. Canonical procedures and validation limits remain in [Trusted Delivery](trusted-delivery.md), [Observability](observability.md), and [Operator Runbook](operator-runbook.md).

- Implemented and live-validated: immutable trusted delivery and historical controlled promotion; structured logging, bounded health metrics, dashboard rendering, healthy-state availability alert inspection, and bounded release review. Read-only live validation for #80 produced a representative `READY / 0`, then a retention-driven `BLOCKED / 3` when source and rendered-artifact protection fell below the 75-minute margin. Both evaluations were read-only and performed no Cloud Deploy action. These observations do not authorize a future action or establish current eligibility.
- Implemented with offline-only coverage: other preflight outcomes and negative cases, review hold/reject scenarios, manual rejection/rollback workflow contracts, and rollback eligibility. No executed rollback or broader performance validation is claimed.
- The first MVP release has been published. The validation limits above remain unchanged by publication.
- Next planned milestone: Online Shop Integration. Application tracing, synthetic monitoring, notification routing, and bounded application error/latency alerting are planned there; they are not part of the completed MVP baseline.
- Deferred beyond that integration: automated promotion/rollback, SLO-based release gates, and broader performance validation. No SLO implementation is required for the Online Shop milestone.

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
* record the published MVP tag and GitHub Release reference in the canonical release documentation

### Target outcome

The first MVP release has been published, packaging a coherent end-to-end platform story with explicit validation limits. The implemented platform can:

* build and identify an immutable release candidate
* verify and attest that candidate
* enforce admission trust
* promote the same release across environments
* correlate runtime behavior with release identity
* evaluate release eligibility before promotion or rollback
* preserve separate authorization for deployment mutations

---

## Online Shop Integration

**Goal:** Integrate the instrumented Online Shop application into the existing trusted delivery path and validate application behavior with Google Cloud observability and synthetic monitoring.

### Scope

* retain Application Modernization Lab as the canonical application source; select a full immutable source commit and reuse its documented build inputs and runtime contracts
* implement a repeatable Cloud Build source-selection and build path for the selected Online Shop components, publishing their images to Artifact Registry with accurate source/build/digest metadata
* extend the current single-image release model to a complete, immutable application image set, with component-specific source, build, verification, and trust references
* define the verification and admission treatment of external dependencies such as Redis, and of supporting images such as the Collector; preserve enforced admission without blanket exceptions
* reuse the separate verification, signing, and Binary Authorization boundaries for application images; successful builds or healthy runtime signals do not establish trust
* prepare digest-pinned deployment configuration, environment parameters, resource requests/limits, and the required Cloud Deploy rendering and release-control adaptations
* assess actual GKE capacity before deployment; begin in dev with one instrumented service and its required dependencies, then expand to the components needed for the selected end-to-end application scenario
* preserve the existing sample service as a platform reference workload during integration
* configure OpenTelemetry collection and export for the signals actually implemented by the selected application revision: Cloud Logging, Cloud Monitoring / Managed Service for Prometheus, and Cloud Trace as appropriate
* define service, environment, and version correlation; validate cross-service trace propagation and avoid duplicate log or metric ingestion
* adapt application metric queries and dashboards to Online Shop semantics rather than assuming compatibility with sample-service log-based metrics
* establish bounded normal application traffic and explicit health-probe filtering; validate request activity, server errors, latency, and workload availability, treating missing data as missing evidence
* define the monitor's network path and application endpoint access before provisioning uptime checks or synthetic execution
* add an uptime check for endpoint availability and a scripted Google Cloud synthetic monitor for a selected user journey, such as catalog browsing and cart operations, with isolated test data and cleanup
* configure actionable application and synthetic-failure alert policies with notification routing; set latency thresholds only after obtaining a meaningful traffic baseline
* exercise a bounded failure and recovery scenario in dev, confirming detection, incident opening, notification receipt, diagnosis through correlated telemetry, and incident closure
* demonstrate a subsequent application update using the same build and release interfaces, with telemetry correlated to the deployed image set
* validate controlled progression through dev, stage, and prod after dev acceptance and capacity review, preserving the same trusted application image set across environments
* document repeatable deployment, telemetry inspection, synthetic checks, failure recovery, validation limits, and sanitized durable evidence

This is an independent Secure Delivery Platform delivery path consuming the canonical AML source. It does not depend on or extend the separate AML → CI Build Platform → Container Platform → SRE Platform integration. Application fixes and instrumentation changes remain owned by AML; delivery and environment configuration remain owned by Secure Delivery Platform.

Implementation proceeds from a single-service dev validation to the selected application journey, then telemetry and synthetic acceptance, and finally controlled environment progression. The accepted release records every required application/dependency image; omitted optional components and unimplemented instrumentation are explicit. Collector infrastructure has its own reviewed deployment and image policy.

SLOs, automated promotion/rollback, exhaustive instrumentation of every component, load testing, and production-scale capacity are outside this milestone. Runtime evidence continues to support explicit release review and does not authorize deployment mutations.

### Target outcome

A pinned Online Shop source revision can be built, verified, attested, and deployed through Secure Delivery Platform as a traceable, digest-pinned application release. The same trusted image set can progress through dev → stage → prod without rebuilding; environment-specific configuration remains explicit.

One repeatable user journey produces observable application signals, including a distributed trace across the participating instrumented services. A synthetic monitor validates that journey. A controlled dev failure produces a diagnosable incident and a delivered notification, followed by confirmed recovery and incident closure. A later application update reuses the established delivery interfaces and preserves runtime release correlation.

The milestone is complete only when these behaviors have linked evidence; configuration presence, empty dashboards, and non-firing alerts alone are insufficient acceptance.

---

## Security and Operational Hardening

**Goal:** Strengthen the completed MVP and Online Shop integration, and validate their behavior under broader failure conditions.

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
11. build, signing, deployment, review, and operational responsibilities remain separated by clear IAM and trust boundaries;
12. a pinned Online Shop source revision produces a complete, traceable application image set that progresses through the trusted delivery path without rebuilding between environments;
13. an Online Shop user journey is observable through the implemented application signals and a synthetic monitor, with a controlled failure demonstrating notification delivery, diagnosis, recovery, and incident closure;
14. a subsequent Online Shop update reuses the established source-selection, build, release, and deployment interfaces while preserving runtime release correlation.
