# Roadmap

## Roadmap principle

Secure Delivery Platform provides a trusted software delivery path: immutable artifacts, independent verification, separate signing, enforced admission, controlled promotion and verified rollback. Google Cloud services support these outcomes within a focused, cost-aware learning platform.

The core delivery foundation and Microservices Workload Integration are complete. The remaining plan covers infrastructure lifecycle and recovery alongside trusted release promotion and rollback. The final delivery milestone produces platform v0.3.0.

## Current implementation and validation boundaries

- The core MVP delivered trusted release contracts, executable build/verification/signing, admission, historical sample-service dev → stage → prod promotion, operational visibility and fail-closed release controls. [Platform v0.1.0](https://github.com/DimitryZH/secure-delivery-platform/releases/tag/v0.1.0) is published.
- Microservices Workload Integration is complete and [platform v0.2.0](https://github.com/DimitryZH/secure-delivery-platform/releases/tag/v0.2.0) is published. [Recorded acceptance](online-shop-acceptance.md) covers the complete Online Shop in dev, HTTPS/WAF, attributed telemetry, synthetic/incident validation and manual stop/resume. 429 verification remains deferred; historical PromQL NO_DATA remains an accepted reconstruction limitation.
- [Retained-project cold recovery](cold-recovery-and-teardown.md#verified-retained-project-recovery) is complete as a verified manual procedure. Persistent application-data recovery and repeatability of a subsequent lifecycle cycle remain future work.
- Online Shop is the active workload. Sample-service is retired with no restoration or health gate; its [historical results](historical/sample-service/README.md) remain part of the platform's delivery history.
- Recorded acceptance describes bounded executions, not continuous live health. Online Shop stage/prod promotion and an executed release rollback remain unproven. Stage/prod are learning-platform environments in a shared cluster, not production readiness, HA or independent failure domains.

[Trusted Delivery](trusted-delivery.md), [Observability](observability.md), the [Operator Runbook](operator-runbook.md) and the [complete workload procedure](../deploy/online-shop/complete-README.md) define the implemented contracts and operating limits. Preflight evaluates fresh, independently reviewed, operator-supplied evidence; review, eligibility, action authorization, target approval and execution remain separate. READY establishes eligibility only.

## Milestone and release sequence

| Milestone | Status | Platform release checkpoint |
| --- | --- | --- |
| [Trusted Release Model](#trusted-release-model) | Complete | Core MVP foundation |
| [Executable Foundation](#executable-foundation) | Complete | Core MVP foundation |
| [Trusted Delivery Path](#trusted-delivery-path) | Complete | Core MVP foundation |
| [Controlled Promotion](#controlled-promotion) | Complete | Core MVP foundation |
| [Operational Visibility](#operational-visibility) | Complete | Core MVP foundation |
| [Platform Release Controls](#platform-release-controls) | Complete | Core MVP foundation |
| [MVP Release](#mvp-release) | Complete | v0.1.0 published |
| [Microservices Workload Integration](#microservices-workload-integration) | Complete | v0.2.0 published |
| [Infrastructure Lifecycle, Backup & Recovery](#infrastructure-lifecycle-backup--recovery) | Manual cold recovery complete; lifecycle/data work planned | Separate lifecycle completion |
| [Trusted Release Promotion & Rollback](#trusted-release-promotion--rollback) | Planned | v0.3.0 |

The future lifecycle and application-data backup/restore work is independent of the v0.3.0 release checkpoint.

Platform versions identify implementation and contracts; application release-set identities and image digests are separate records. Publishing a platform tag neither rebuilds nor promotes an application.

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

<a id="online-shop-integration"></a>

## Microservices Workload Integration

**Status:** Complete; platform [v0.2.0 published](https://github.com/DimitryZH/secure-delivery-platform/releases/tag/v0.2.0).

**Goal:** Integrate a representative microservices workload through the trusted delivery path with protected HTTPS and attributable operational signals.

### Delivered scope and outcome

The accepted dev integration includes ten Online Shop application services, ephemeral Redis and a separately trusted Collector. Recorded results cover immutable component/release identity, independent verification and signing, protected deployment and admission, a bounded checkout journey, HTTPS and WAF enforcement, application telemetry and dashboards, scheduled synthetic checks, a controlled availability incident and repeated manual stop/resume.

[Consolidated acceptance](online-shop-acceptance.md) records the executions and accepted 429/PromQL limitations. [Workload architecture](architecture/online-shop.md), the [deployment guide](../deploy/online-shop/complete-README.md) and [incident evidence](../monitoring/online-shop/incident-acceptance.md) retain the technical detail. This milestone establishes the endpoint and telemetry foundations for subsequent trusted release promotion and rollback.

---

## Infrastructure Lifecycle, Backup & Recovery

**Status:** Verified manual cold recovery complete; lifecycle simplification and persistent-data validation planned.

**Goal:** Make infrastructure lifecycle operations repeatable and verify recovery of infrastructure, artifacts and selected persistent application data.

### Scope

- Build on the prepared local recovery kit, completed teardown preserving the project and agreed resources, and successful retained-project cold recovery. Infrastructure/state, immutable images, trust associations, Online Shop, HTTPS and monitoring were restored through a verified manual procedure.
- Simplify and systematize the proven teardown/recovery steps, making required manual actions and continuation after partial execution explicit.
- Verify repeatability and measure recovery time during the next planned lifecycle cycle.
- Execute one bounded persistent application-data backup/restore scenario, checking integrity and measuring RPO/RTO.

### Outcome and completion

A documented, repeatable lifecycle procedure and one verified application-data restore have measured results and clear limits. The [completed cold recovery](cold-recovery-and-teardown.md#verified-retained-project-recovery) does not establish full automation, success of the next cycle or persistent application-data recovery; historical application data, logs and metrics were outside that execution.

---

## Trusted Release Promotion & Rollback

**Status:** Planned; final milestone of the core delivery path, packaged in platform v0.3.0.

**Goal:** Complete the trusted delivery cycle for an updated application workload release and demonstrate controlled promotion and rollback.

### Scope

- **Updated workload release:** Pin a new application revision and use the existing build → independent verification → signing → admission path. Preserve component, source, build, digest and release-set identities; explicitly reuse compatible supporting artifacts where appropriate.
- **Environment progression:** Promote the same trusted application image set through dev → stage → prod without rebuilding. Review environment-specific configuration and capacity, apply required approvals and existing preflight controls, preserve release identity and verify actual running digests.
- **Failed update and rollback:** Execute one bounded failed-update scenario and roll back to an eligible previous trusted release. Verify restored digests, runtime health and telemetry attribution, then clean up scoped test data and temporary resources.
- **Health evaluation:** Define clear success/failure criteria using existing health, telemetry and synthetic interfaces to assess promotion and recovery.
- **Focused supply-chain evidence:** Inspect vulnerabilities, record SBOMs and applicable native Cloud Build provenance for selected release artifacts. Use findings in release review and record accepted exceptions, without an unsupported SLSA-level claim or a universal zero-vulnerability requirement.

### Outcome and completion

Sanitized acceptance evidence demonstrates that the updated trusted image set traverses all three environments without rebuild and that an eligible trusted release is restored after a failed update. Canonical documentation, operator entry points and remaining limitations agree with the accepted behavior. Final release review and publication of **platform v0.3.0** complete this milestone; sufficient accepted evidence can be reused for publication.

---

## Cross-milestone ownership

- SDP owns artifact trust, controlled promotion and rollback. Advanced SLO-driven delivery, scaling and reliability experiments sit within SRE Platform's scope.
- Application Modernization Lab owns application changes and instrumentation. SDP consumes an updated application workload release and owns its delivery, environment and collection configuration.
- Infrastructure Lifecycle, Backup & Recovery owns lifecycle repeatability and the bounded data-restore scenario. Trusted Release Promotion & Rollback owns changed-release progression, failed-update recovery and the v0.3.0 checkpoint.
- Preserve least-privilege IAM and administrative/recovery access, separate build/verification/signing/deployment authority, Workload Identity, existing Secret Manager usage, Binary Authorization, Cloud Armor, source/digest/evidence verification, execution guards and destruction protections. Keep one active owner per resource/field and one intended collection path per signal.
- Preserve historical evidence and distinguish implementation coverage, recorded-run acceptance and fresh live observations. Automated promotion/rollback, production readiness and HA are outside baseline completion.

## Completion criteria

The core delivery path is complete when linked acceptance evidence demonstrates:

1. The completed foundation and workload integration retain traceable immutable artifacts, independent verification, separate signing, admission enforcement and attributable operational signals.
2. An updated application workload release preserves component/source/build/digest/release-set identity, including explicit compatible supporting-artifact reuse.
3. The same trusted image set progresses through dev → stage → prod without rebuild, with environment configuration/capacity review, required approvals, preflight eligibility and actual-digest verification.
4. One bounded failed update is followed by an executed rollback to an eligible previous trusted release, with restored digests, runtime health, attributed telemetry and scoped cleanup.
5. Existing health, telemetry and synthetic interfaces provide clear success/failure criteria for promotion and recovery; missing evidence is treated explicitly.
6. Selected release artifacts have vulnerability inspection, SBOM and applicable native build-provenance evidence; findings and accepted exceptions are recorded in release review.
7. Review, eligibility, authorization, target approval and execution retain their separate trust and least-privilege boundaries.
8. Canonical documentation, operator entry points, sanitized evidence and accepted limits align, and platform v0.3.0 is published after final release review.

The separate lifecycle milestone is complete when its next planned cycle demonstrates repeatability with measured recovery time and its bounded persistent application-data restore demonstrates integrity with measured RPO/RTO.
