# Microservices Workload Integration acceptance

Documentation review on **2026-11-17 America/Toronto**, using retained executions only.
Technical acceptance is recorded with two explicitly accepted limitations below; final review
and publication remain open in [#133](https://github.com/DimitryZH/secure-delivery-platform/issues/133).
No new health check was made. Nodes are left paused; recorded running results are not current availability.
This document authorizes no traffic, apply, temporary policy rule, lifecycle operation,
rollout, milestone closure or release publication.

## Recorded repeated manual stop/resume: passed

A separately authorized manual cycle completed after permanent workload selectors were
applied. Resume used a fresh full two-pool-count-only plan; the control plan was No changes.
Two nodes and all 14 Shop Pods becameReady automatically;12 workload templates retained the
workload-pool selectors and Collector covered both nodes (2/2). Original DeploymentUIDs,
templates, candidate/artifact references, holds and bootstrap/Kubernetes state were preserved.
No ad hoc eviction, cordon, application rebuild or rollout was needed. Redis was empty.

Runtime acceptance, DNS/system services, metrics, valid HTTPS and healthy frontend backend
passed. Natural HTTPS/synthetic checks succeeded with fresh trace/log/Redis metric evidence.
A complete post-readiness five-minute frontend window had successful request metrics and no
observed error series; the empty alert vector is not a numerical zero-error measurement.
Only the exact approved maintenance snooze ended, after readiness, at 2026-11-16T13:18:43Z;
three policies stayed enabled and subsequent normal checks succeeded, with no OPEN incidents.
Snooze-mediated closures are not incident recovery or notification evidence. Actual #115
notification proof comes from the separately [recorded exercise](../monitoring/online-shop/incident-acceptance.md).

This accepts the recorded cycle, not guaranteed future capacity or durable Redis/Collector
state. No recurring shutdown schedule or budget alert is introduced.

## Recorded application, endpoint and telemetry acceptance

Release `shop-edge-66b636f-f8b585b4`, rollout `dev-edge-001`, completed successfully.
Producing/deployment revision: `66b636f074ac9270a5b2617d27d3261ce0ec1872`;
AML revision: `67b6cd85ae01c698bbf86904d953d5145b7b5820`.
Release set: `sha256:f8b585b4334eddb2a7e4962ca54bfbdbc7fb96e7751083c57d3d3924f7459f25`.
The protected 45-resource render and independent trust/admission guards passed before rollout.
Runtime readback verified exact digests, 14 Ready Pods, permanent workload selectors,
Collector 2/2, Gateway/routes, healthy backend, valid HTTPS and HTTP-to-HTTPS 301.

One bounded checkout on 2026-11-15 used 14 of 20 permitted HTTP requests: browse, product,
currency, cart, checkout and order confirmation passed. Exact-key Redis DEL/EXISTS=0 and owned
port-forward closure passed; other keys were untouched. Signals covered all ten applications,
445 spans, 14 cross-service edges, 402 native-linked component logs, attributed application
and Redis metrics, with no duplicate ingestion in the recorded checks. Seven recommendation
SERVER calls and their catalog downstream calls succeeded without observed DEADLINE_EXCEEDED.
This is one journey, not sustained reliability or load acceptance.

All six published dashboard queries were checked with service/version/environment/release
attribution; each returned ten current-release groups in the recorded window. Request rates,
latency, observed success and available/desired replicas had finite data. Error zero was
supported by positive request denominators; nonexistent-release controls returned no data.
Health probes were excluded from user panels. These successful journey queries do not resolve
the separate historical incident query limitation below.

## Recorded Armor acceptance and accepted 429 deferral

[Sanitized Armor evidence](../deploy/online-shop/armor-validation.json) records preview
SQLi/XSS matches followed by the reviewed enforcement apply. Fresh natural scheduled edge
logs subsequently confirmed enforced priority 2000. Three normal HTTPS GETs returned 200;
SQLi/XSS probes returned 403 with enforced priority 1000/DENY and matching WAF rule IDs.
No application rebuild or rollout was needed for enforcement.

**Accepted limitation: 429 verification deferred.** The bounded twelve-request scoped test
returned only 2000/CONFORM, not temporary 1500 or 429. A later propagation-gated attempt also
observed 2000/CONFORM and stopped before its series. Both temporary rules were removed,
baseline rules restored, recovery GETs returned 200 and full control plans were No changes.
Local header delivery and valid CEL syntax do not establish header visibility at the edge;
the exact mismatch cause is unresolved. Neither the temporary throttle mechanism nor actual
priority-2000 threshold 1200/60s/IP has a confirmed 429 in this environment. Historical proof
from another environment is not substituted. No new test is required by this documentation.

## Accepted historical PromQL NO_DATA limitation

The [read-only analysis](../monitoring/online-shop/promql-incident-limit.md) identifies retained
constant cumulative1 samples and a zero retrospective rate filtered by `>0`. It reproduces
why the current historical query is empty, but cannot reconstruct the original positive
live evaluation. This is not a successful query check or proof of zero errors. Actual alert,
raw counter and native failure/recovery evidence remain valid. The operator accepts this bounded historical reconstruction limit for this review; the
query is not marked passed and the unexplained original positive evaluation remains a limit.
No new incident is required solely to populate a chart.

## Follow-up: final review and platform release

[#133](https://github.com/DimitryZH/secure-delivery-platform/issues/133) owns canonical
architecture/operator/access/telemetry/evidence/limit alignment and the separately authorized
platform v0.2.0 publication after the final acceptance and limitations review. The [roadmap](roadmap.md)
sequence is unchanged. Sample-service is retired; later governance/canary/progression/rollback/
load scenarios remain in milestones9–10. No platform tag or milestone closure is performed here.

## Review checklist

- [x] Retained independent trust, protected render, runtime and bounded journey evidence reconciled.
- [x] WAF preview/enforcement and exact temporary-rule cleanup recorded.
- [x] Repeated stop/resume and bounded incident/notification/recovery evidence linked.
- [x] 429 verification deferred explicitly; no throttle-denial success claimed.
- [x] Historical PromQL NO_DATA accepted as a reconstruction limit, not zero errors.
- [x] [Draft v0.2.0 notes](releases/v0.2.0.md) prepared; platform and application versions separated.
- [ ] Review and merge documentation in #133; agree the exact future platform release commit.
- [ ] Separately authorize tag/release publication. No tag/release is created here.
- [ ] Prepare and validate a cold-recovery kit outside the GCP project.
- [ ] Separately review and authorize complete cloud-resource removal after that recovery gate.

## Next stage: cold recovery and full cloud removal — not performed

Prepare an independently accessible, integrity-checked kit outside the project: source/pins,
provider locks, environment/backend reconstruction instructions, protected Terraform state
backups, exact image manifests/configs/layers, candidate bytes and signing/provenance evidence,
synthetic source ZIPs, DNS delegation and secrets/access recovery procedures. A candidate JSON
is not a container-image backup. Document which non-exportable trust keys require new keys,
new registry references and fresh verification/signing; do not promise that old attestations
transfer to new identities. Keep secrets/state private and preserve human administrative access.

Validate recovery in isolation before proposing removal. Inventory all owners, holds and
prevent_destroy protections; require a separately reviewed destructive plan. Remove Gateway/
controller-managed LB resources while the cluster can reconcile them, then runtime and the
remaining scoped cloud resources, including persistent artifacts/trust/evidence/state only
after verified external preservation. This is full removal, not the existing node pause.
DNS/provider access and retained external-domain responsibilities need their own cutover plan.
Neither the kit, a cold restore nor complete deletion has been executed or accepted here.
