# Roadmap

## Roadmap principle

The Secure Delivery Platform is organized around a trusted software delivery path.

The implementation sequence follows the release trust model: define release identity and trust boundaries, establish the executable foundation, enforce deployment trust, introduce controlled promotion, connect runtime evidence to release decisions, and turn those decisions into executable platform controls. After the core MVP, integrate Online Shop as a representative workload, strengthen platform governance and security, then validate controlled updates, recovery and resource efficiency.

Google Cloud services are implementation tools for these outcomes. Each addition has a bounded operational scenario, an explicit owner and acceptance evidence. The platform remains focused on secure delivery rather than becoming a generic CI/CD framework, Terraform framework or broad SRE platform.

---

## Current implementation and validation boundaries

This roadmap describes sequence and scope, not proof that every scenario below has been executed. Canonical procedures and limits remain in [Trusted Delivery](trusted-delivery.md), [Observability](observability.md), [Operator Runbook](operator-runbook.md), and the [complete workload integration](../deploy/online-shop/complete-README.md).

- Milestones 1–7 delivered the core MVP and published platform release [v0.1.0](https://github.com/DimitryZH/secure-delivery-platform/releases/tag/v0.1.0).
- Historical core validation includes immutable trusted delivery and controlled promotion; structured logging, bounded health metrics, dashboard rendering, healthy-state availability alert inspection, and release review. Read-only validation for #80 produced a representative `READY / 0`, then retention-driven `BLOCKED / 3` when source/rendered-artifact protection fell below 75 minutes. These observations do not establish current eligibility or authorize a future action.
- Other preflight outcomes and negative cases, review hold/reject scenarios, manual rejection/rollback contracts and rollback eligibility have offline coverage. An executed release rollback and broader performance validation are not yet established.
- Milestone 8 is in progress. [#87](https://github.com/DimitryZH/secure-delivery-platform/issues/87), [#93](https://github.com/DimitryZH/secure-delivery-platform/issues/93), and [#100](https://github.com/DimitryZH/secure-delivery-platform/issues/100) accepted trusted catalog delivery and then the complete ten-service Online Shop plus Redis in dev, with a separately trusted Collector. Recorded evidence covers source/build/digest verification, eleven-member attestation, protected Cloud Deploy rendering/preflight, full runtime, a bounded checkout journey, negative admission, scoped cleanup and sample-service preservation.
- The preserved 2026-11-03 journey passed the merged signals validator with its normal independent guard. It demonstrates recorded distributed traces, attributed application/Redis metrics and native correlated logs for all ten application components. This recheck does not establish current runtime health or continuous telemetry. Historical failures, startup export losses, the fixed clock allowance and observation limits remain in the canonical evidence.
- Domain-based HTTPS access, application dashboards, Managed Service for Prometheus integration, uptime/synthetic checks, notification delivery and the bounded application incident flow remain planned in milestone 8.
- Governance/security extensions are planned in milestone 9. A subsequent application update, canary, full-workload environment progression, executed rollback and bounded autoscaling/load validation are planned in milestone 10.
- Automated promotion/rollback, exhaustive instrumentation, production-scale load validation, durable Redis/Collector storage and multi-cluster or multi-region HA are not baseline completion requirements of this roadmap.

Preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize or execute an action. Review, eligibility, action authorization, target approval and execution remain separate boundaries; READY is eligibility only.

---

## Milestone and release sequence

| Milestone | Name | Platform release checkpoint |
| --- | --- | --- |
| 1 | Trusted Release Model | |
| 2 | Executable Foundation | |
| 3 | Trusted Delivery Path | |
| 4 | Controlled Promotion | |
| 5 | Operational Visibility | |
| 6 | Platform Release Controls | |
| 7 | MVP Release | v0.1.0 published |
| 8 | Online Shop Integration | v0.2.0 planned after acceptance and documentation |
| 9 | Platform Governance & Hardening | Internal completion checkpoint; no required separate release |
| 10 | Controlled Delivery & Reliability | v0.3.0 planned after acceptance and documentation |

GitHub milestone 8 retains the public name **Microservices Workload Integration**; its roadmap section remains **Online Shop Integration**.

Platform versions identify the platform implementation and contracts. Application release-set identities and image digests are separate records. Publishing a platform tag neither rebuilds nor automatically promotes an application.

For v0.2.0 and v0.3.0, complete the relevant milestone acceptance, align canonical documentation, record changes and known limits, and link the accepted sanitized evidence before publication. Reuse sufficient existing evidence; repeat scenarios only where changed behavior, missing evidence or unresolved failures require it. Neither future release is published by this roadmap update.

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

**Goal:** Complete the instrumented Online Shop integration with a usable HTTPS endpoint, application observability and repeatable synthetic/incident validation.

### Accepted integration baseline

The accepted dev integration comprises all ten application services (`frontend`, `productcatalogservice`, `cartservice`, `currencyservice`, `recommendationservice`, `adservice`, `checkoutservice`, `shippingservice`, `paymentservice`, and `emailservice`), the explicit `redis-cart` dependency, and Collector support under its separate image policy.

Immutable AML application/dependency contracts, component build/verification/signing, complete release identity, dev deployment, the bounded checkout journey and recorded telemetry acceptance are implemented. Loadgenerator is excluded from the steady application set; optional assistant/packaging backends remain disabled. Any future validation image requires explicit verification/admission treatment and a bounded execution scope.

### Remaining scope

* establish a selected hostname under the platform domain, such as `shop.runtimeplatforms.dev`, using Cloud DNS and scoped subdomain delegation where appropriate; preserve existing domain services
* expose only the intended frontend through GKE Gateway API and a reviewed external Application Load Balancer, with stable addressing, Certificate Manager TLS and a tested HTTPS path
* select the Gateway/LB configuration with future Cloud Deploy canary and IAP compatibility in mind; record regional/global choice, access boundaries and recurring costs
* configure a bounded Cloud Armor baseline, including evaluated WAF rules and rate limiting; verify allowed and denied requests before enforcing selected rules
* adapt queries and dashboards to actual Online Shop semantics: request activity, errors, latency, availability and component/version/environment/release attribution
* integrate Google Cloud Managed Service for Prometheus and PromQL where appropriate, using an explicitly owned collection/export path and avoiding duplicate ingestion of the same series
* retain cross-service propagation and native trace/log correlation; explicitly filter health traffic, control metric cardinality and preserve the accepted source/build/digest relationship
* define monitor network access and endpoint authentication before provisioning an uptime check and a scripted Google Cloud synthetic monitor
* validate a selected synthetic user journey using isolated test data, bounded frequency/traffic and exact cleanup
* configure actionable application and synthetic-failure alerts with notification routing; establish a meaningful baseline before choosing latency thresholds and treat missing data as missing evidence
* exercise one bounded application/dependency availability failure in dev; confirm detection, incident opening, notification receipt, telemetry-based diagnosis, recovery and incident closure
* preserve sample-service in dev/stage/prod and recheck capacity/artifact protection before separately authorized live changes
* align public architecture, deployment/access instructions, telemetry inspection, synthetic/incident runbooks, validation limits and sanitized durable evidence

This is an independent SDP path consuming canonical AML source. It does not depend on the separate AML → CI Build Platform → Container Platform → SRE Platform integration. Application fixes/instrumentation remain owned by AML; delivery, environment and collection configuration remain owned by SDP.

### Target outcome and acceptance

The complete trusted application is usable through the selected HTTPS hostname. Its bounded normal and synthetic journeys produce attributable signals and useful dashboard results. A controlled dev failure produces a delivered notification and a diagnosable incident, followed by confirmed recovery and closure.

The accepted dev release, endpoint/TLS/protection checks, meaningful dashboard/query results, synthetic executions, incident lifecycle, cleanup and sample health have linked sanitized evidence. Empty dashboards, configuration presence and non-firing alerts alone are insufficient.

A subsequent application update, full-workload stage/prod progression, canary, release rollback, SLI/SLO-based release evaluation and autoscaling/load experiments belong to milestone 10. Milestone 8 establishes their endpoint and telemetry foundations without implementing those scenarios twice.

### Platform release checkpoint

After milestone 8 acceptance and canonical documentation alignment, publish **platform v0.2.0**. Release notes link the accepted integration/observability evidence and state its limits. Publication is a separate action and does not imply production hardening, HA or completion of milestones 9–10.

---

## Platform Governance & Hardening

**Goal:** Strengthen infrastructure ownership, build isolation, supply-chain evidence, access control and auditability before advanced delivery and scaling exercises.

### Scope

* introduce Infrastructure Manager for a selected real Terraform module using supported runtime/provider versions, explicit execution identity and managed state ownership; review preview/apply behavior and document compatibility
* keep full-foundation migration a separate decision based on that experience; the same resources must not be actively managed by both the existing Terraform state and Infrastructure Manager
* implement a Cloud Build Private Pool scenario with a concrete private-connectivity requirement, reviewed dependency egress and least-privilege execution; verify the intended network boundary and cost
* preserve distinct build, verification/signing and deployment authority, and continue source/configuration/build/plan/digest verification when adapting execution environments
* establish Artifact Analysis vulnerability inspection and SBOM records for selected release artifacts; define how findings enter explicit release review and how exceptions are bounded
* record and validate applicable native Cloud Build provenance, keeping it distinct from platform admission attestations; claim a SLSA assurance level only where the actual build/input path supports it
* use Policy Troubleshooter for a real access problem, Policy Simulator for a proposed IAM change where supported, and IAM Recommender as input to reviewed permission reduction; preserve required operational/recovery access
* demonstrate versioned Secret Manager consumption, least-privilege access, rotation and restoration of a previous version for a real platform integration; reuse workload identity rather than introducing long-lived service-account keys
* synchronize selected cluster/platform configuration through Config Sync, with explicit ownership for namespaces, RBAC, quotas and policy resources
* introduce Policy Controller with scoped audit/dry-run evaluation followed by tested enforcement of selected constraints; review necessary narrow exceptions for supporting infrastructure
* validate NetworkPolicy boundaries against actual service dependencies, including allowed consumers of Redis, before enforcing selected restrictions
* establish IAP access for an appropriate dev/stage endpoint, with explicit user/service identities, approved access and denied-access evidence; retain the intended public demonstration path
* use Cloud Asset Inventory to review the project's resource and IAM inventory and investigate a representative unexpected change
* build an operational audit trail using Cloud Audit Logs and focused SQL analysis; select Data Access logging scope, retention and volume deliberately, and verify a useful sensitive-change alert
* tighten environment-specific trust and access policies, improve verification/admission denial diagnostics, remove unnecessary permissions and temporary implementation exceptions, and validate release metadata consistency
* document ownership, recovery procedures, accepted configuration and evidence in focused runbooks without turning each service into a separate delivery framework

Config Sync owns only the declared platform resources. Cloud Deploy continues to own application release resources. Policy Controller constraints and infrastructure policies complement Binary Authorization; they do not replace image admission trust. The current dev/stage/prod namespaces share a cluster and are not independent failure domains.

### Target outcome and acceptance

A selected infrastructure module is managed through Infrastructure Manager with one clear state owner. Private Pool networking and execution identities satisfy their reviewed scenario. Selected artifacts have usable vulnerability/SBOM/provenance evidence, and release review states how that evidence affects eligibility.

Permission changes, secret-version changes, policy synchronization/enforcement, network restrictions and IAP access have bounded successful/denied test results. Operators can identify resources and trace representative sensitive actions through inventory and audit records. Existing workload delivery and sample-service remain compatible.

Every adopted capability has a defined scenario, owner, cost boundary, acceptance result and documented limitation. Broader organization/fleet rollouts, automatic application GitOps and an unconditional migration of the full foundation are outside this milestone.

### Completion checkpoint

Milestone 9 has its own reviewed completion/evidence checkpoint. **No separate platform release is required after milestone 9**; its results are packaged with milestone 10 in v0.3.0.

---

## Controlled Delivery & Reliability

**Goal:** Demonstrate safe application updates, environment progression, recovery and resource efficiency using the governed platform.

### Delivery and release scope

* select a subsequent immutable AML application revision and produce its traceable complete application image set using the established build/release interfaces; reuse compatible artifacts explicitly and preserve component-specific identity
* adapt exact inventory, metadata and runtime checks for reviewed stable/canary resources and bounded replica ranges while retaining digest, membership and admission enforcement
* implement a Cloud Deploy canary for a selected stateless component with explicit stable/canary routing, phase weights, controlled traffic and component/version-aware telemetry
* define one useful SLI/SLO and error-budget view; establish baseline/error/latency measurements and an explicit decision when evidence is absent or insufficient
* connect deployment verification or analysis to real observed metrics, documenting success/failure criteria and operator decisions; metric collection alone is not an automatic promotion gate
* progress the same trusted application image set through dev → stage → prod after environment-specific capacity, configuration, admission and protected-artifact review, without rebuilding between environments
* execute a bounded failed-update scenario and a controlled rollback to an eligible previous trusted release; verify running digests, recovery, telemetry attribution and sample-service health
* perform a small blue-green comparison after the canary baseline, recording switching/recovery behavior and temporary resource cost; canary remains the primary progressive delivery strategy

### Scaling and cost scope

* introduce HPA for a selected stateless workload with bounded min/max replicas, explicit metric ownership and a measured scale-out/scale-in scenario
* deploy VPA in recommendation mode, evaluate its resource recommendations, and treat any automatic application as a separately reviewed bounded experiment compatible with HPA
* exercise Cluster Autoscaler where node capacity must follow workload scaling, with reviewed limits, quotas, scheduling constraints and a bounded cost envelope
* define ownership for replica counts and resource requests so HPA, VPA, Cloud Deploy, Config Sync and Terraform do not continuously overwrite one another
* run limited-duration load tests with isolated data, a known traffic budget, observable scaling/recovery and exact cleanup; do not extrapolate results into production-scale capacity
* use Billing budgets, cost attribution and Google Cloud Recommender to evaluate resource sizing, idle capacity and observability costs; budget notifications are not hard spending caps
* retain the resulting configuration or remove temporary experimental resources according to the reviewed operating/cost decision

### Target outcome and acceptance

A new application version traverses the existing trusted delivery interfaces. A canary is evaluated using real attributed telemetry; one rejected/failed update has an executed recovery path. The same accepted image set reaches the reviewed environments without rebuild. Release-set/source/build/digest identities remain distinguishable from environment configuration and validator versions.

HPA behavior, VPA recommendations, the selected node-scaling scenario and limited load test have measured results within their defined bounds. The blue-green comparison and resource/cost decisions have linked evidence. Application and sample health, synthetic data cleanup and temporary-resource cleanup are verified after the exercises.

Canonical architecture, operator/deployment/recovery/scaling instructions, change history and validation limits are aligned with the final implementation. Production-scale throughput, durable Redis/Collector state, automatic promotion/rollback and multi-cluster/multi-region HA remain outside baseline acceptance.

### Platform release checkpoint

After milestone 10 acceptance and final documentation alignment, publish **platform v0.3.0**, packaging the accepted results of milestones 9 and 10. Include release notes, repeatable operator entry points, evidence references and remaining limitations. No additional live exercise is required solely to create a tag when sufficient accepted evidence already exists.

---

## Cross-milestone execution and ownership

- Milestone 8 owns endpoint/telemetry foundations and the application availability incident. Milestone 9 owns governance, access/security boundaries and their enforcement checks. Milestone 10 owns changed-release progression, rollback and scaling behavior.
- Select Gateway/routing and metric collection interfaces in milestone 8 with canary, IAP and autoscaling compatibility in mind. Extend them later rather than introducing parallel paths.
- Use one active owner per resource/field and one intended collection path per metric/log stream. State or controller ownership changes require an explicit transition.
- Group implementation into coherent issues and reviewable changes. A service name alone is not a requirement for its own issue or pipeline.
- Infrastructure changes, public access, failure exercises, load/scaling bounds and deployment mutations use their reviewed scope and separate authorization. Runtime health, a successful build and READY eligibility do not authorize a mutation.
- Preserve accepted historical records and clearly distinguish implementation tests, recorded-run acceptance and current live observations.

---

## Completion criteria

The roadmap is complete when linked evidence demonstrates that:

1. a source revision produces a uniquely traceable release candidate;
2. the resulting artifacts are identified by immutable image digests;
3. independent verification determines whether candidates can receive the required trust signal;
4. deployment policy prevents untrusted images from running where admission is enforced;
5. the same trusted image set progresses through dev → stage → prod without rebuild;
6. running workloads remain correlated with their component source/build/digest and release identity;
7. useful operational health, application telemetry and synthetic results are available for release review;
8. promotion and rollback eligibility are evaluated by deterministic, executable, fail-closed controls;
9. release review, eligibility, authorization, target approval and execution remain separate boundaries;
10. failed verification, denied deployment, rejected/failed release actions and recovery have explicit diagnosable outcomes;
11. build, signing, infrastructure and deployment responsibilities retain clear least-privilege boundaries;
12. the complete Online Shop workload is usable through its reviewed HTTPS endpoint, with explicit application/dependency/supporting inventory and trust treatment;
13. a bounded normal/synthetic journey has attributable distributed traces, application metrics and native correlated logs, without duplicate ingestion in the validated window;
14. a controlled application failure demonstrates notification receipt, diagnosis, recovery and incident closure;
15. selected managed infrastructure, private-build networking, supply-chain evidence, secrets and cluster/access policies have explicit ownership and accepted operating scenarios;
16. inventory and audit records support investigation of representative resource/IAM and release-related actions;
17. a subsequent application update demonstrates canary, controlled environment progression and eligible rollback with preserved release correlation;
18. bounded autoscaling/load observations and resource/cost analysis substantiate the chosen operating limits;
19. canonical documentation and sanitized durable evidence describe the implemented behavior and its limits;
20. platform v0.2.0 is published after milestone 8, and platform v0.3.0 after milestone 10; milestone 9 has a completion checkpoint without a required separate release.
