# Milestone 8 technical acceptance checkpoint

Recorded review on **2026-11-16 America/Toronto**. Milestone 8 remains **in progress**.
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

## Remaining technical gate: Armor

The [bounded Armor plan](../deploy/online-shop/armor-acceptance.md) is prepared, not executed.
Live1000/2000 rules remain preview. A full enforcement plan changes only Armor and its operator
output, with an explicitly documented unused ban-field normalization. Current active WAF
preview-denial evidence is missing; a capped capture of normal rate-preview logs shows ACCEPT.

Review/merge enforcement-aware validator changes before live use. Review missing preview
probes and the saved plan, then separately authorize apply and bounded HTTPS/WAF403/scoped
throttle429/cleanup acceptance. The actual1200/60s threshold result remains separate from
a low-threshold mechanism test. Do not claim enforcement merely from configuration or a plan.

## Historical PromQL limit: proposed explicit disposition

The [read-only analysis](../monitoring/online-shop/promql-incident-limit.md) identifies retained
constant cumulative1 samples and a zero retrospective rate filtered by `>0`. It reproduces
why the current historical query is empty, but cannot reconstruct the original positive
live evaluation. This is not a successful query check or proof of zero errors. Actual alert,
raw counter and native failure/recovery evidence remain valid. Explicit acceptance of this
bounded reconstruction limit is proposed for final review; it is not silently resolved.
No new incident is required solely to populate a chart.

## Follow-up: final review and platform release

[#133](https://github.com/DimitryZH/secure-delivery-platform/issues/133) owns canonical
architecture/operator/access/telemetry/evidence/limit alignment and the separately authorized
platform v0.2.0 publication after every mandatory gate is accepted. The [roadmap](roadmap.md)
sequence is unchanged. Sample-service is retired; later governance/canary/progression/rollback/
load scenarios remain in milestones9–10. No platform tag or milestone closure is performed here.
