# Observability

## Current visibility baseline

Current delivery supplies annotations, rollout/job results, readiness, digest inspection, and manual internal HTTP checks. The [runtime release correlation procedure](operator-runbook.md#runtime-release-correlation) composes these existing sources into a read-only baseline:

```text
Environment / namespace → Deployment / owned Pods → running immutable digest
  → source revision → producing build → verification context → trust reference
  → Cloud Deploy release → target rollout → rollout state
```

The procedure compares the Pod template and actual Pods with release annotations, uses Cloud Deploy resource labels to locate the release, and checks the target snapshot against the cluster and deployment authority. Missing evidence, inconsistent identity, an unsettled workload, or multiple possible rollouts stop correlation. No release database, new workload, or infrastructure mutation is required.

Runtime annotations, verification status, and trust references are correlation evidence, not cryptographic proof. Attestation inspection and Binary Authorization remain separate trust controls. A successful rollout or healthy Pod does not prove provenance or authorize promotion.

Platform Logging/Monitoring access does not imply application dashboards, metrics, alerts, or automated release decisions exist.

Operational Visibility remains an architectural capability in the [Roadmap](roadmap.md), answering what runs, where, when it changed, and whether it behaves normally.

## Structured application logging

`sample-service` implements newline-delimited JSON stdout for startup and HTTP responses using the Python standard library. Request events identify service/environment, method, URL path, HTTP status, monotonic duration in `latency_ms`, severity, and health-check traffic. Query values, headers, bodies, cookies, and URL authority are excluded. Responses and exact-path health routing are unchanged. One flushed event accompanies each HTTP response; closed idle connections produce no request event.

The existing GKE workload logging integration collects container stdout/stderr and adds Kubernetes resource identity. JSON events can be inspected as `jsonPayload`, with severity extracted into the LogEntry `severity` field. Use the [read-only application log procedure](operator-runbook.md#application-log-inspection) to filter a selected environment and Pod, then apply runtime release correlation to that same workload. Full release metadata is not copied into every event.

Repository validation covers application responses, JSON shape, latency, severity, health traffic, and sensitive request-data exclusion. The baseline was live-validated in dev through the trusted build, verification, attestation, protected release, and rollout path. Runtime digest and release correlation checks passed; internal GET `/` and `/healthz` returned HTTP 200. Cloud Logging ingested structured request and startup events from the new Pod, with `/healthz` marked `health_check=true` and severity extracted into the top-level LogEntry field. Stage and prod remained unchanged; no promotion or approval occurred. Kubernetes resource labels correlate logs to the producing workload. Logs remain operational/runtime evidence, not cryptographic proof; release metadata, attestation, and Binary Authorization establish separate correlation and trust properties.

The logging capability adds no dashboards, alerts, tracing, SLOs, sinks, exports, custom retention, or additional logging backend. Health probes produce request events and contribute to logging volume; queries can exclude them without changing collection or retention. See [GKE collection](https://docs.cloud.google.com/kubernetes-engine/docs/concepts/about-logs) and [structured payload handling](https://docs.cloud.google.com/logging/docs/structured-logging).

## Release-health metrics

The repository defines three [log-based metrics](../monitoring/log-based-metrics/README.md) in the existing Terraform foundation: HTTP response activity, HTTP 4xx/5xx errors, and a millisecond latency distribution. Their common filter selects only structured sample-service request events from the configured cluster, with matching dev/stage/prod namespace and environment and explicit health classification. Only environment and health-check user labels are extracted; full release identity stays in runtime correlation. Built-in GKE resource labels still create per-Pod series, so custom labels are bounded but total cardinality depends on workload churn. Health traffic can be included or excluded intentionally. The three metrics were created through a reviewed Terraform plan and exact saved-plan apply, with no changes to existing infrastructure. The baseline was live-validated in dev: request and latency series were observed, `health_check=true` was distinguishable, deployment-state metrics showed available replicas equal to desired replicas, and runtime release correlation remained consistent. The error metric existed without series because no matching 4xx/5xx logs occurred in the observation window. No artificial failures were generated; `health_check=false` was not observed in that window.

Workload availability uses the existing GKE deployment-state `prometheus.googleapis.com/kube_deployment_status_replicas_available/gauge` alongside `prometheus.googleapis.com/kube_deployment_spec_replicas/gauge`. Read-only inspection confirmed these signals already report the dev workload; no new Managed Service for Prometheus configuration, custom availability metric, or collector is introduced. Compare fresh available replicas with desired replicas for the same deployment/environment. A positive desired count with equal available replicas is the bounded availability signal; zero desired replicas or missing/stale data is not healthy application evidence. Confirm Deployment observed generation and Pod readiness through the existing runtime procedure. Container uptime alone would not prove readiness. See [GKE deployment-state metrics](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/kube-state-metrics).

Use [release-health metric inspection](operator-runbook.md#release-health-metric-inspection) for read-only Monitoring queries and release correlation. Metrics describe operational behavior, not artifact provenance, verification success, attestation validity, or Binary Authorization admission. A healthy signal never authorizes promotion. Metrics do not add dashboards, alerts, SLOs, tracing, exports, another backend, or automated decisions.

## Deployment health dashboard

One compact [deployment health dashboard](../monitoring/dashboards/README.md) is defined declaratively for sample-service, with a dev/stage/prod selector and five views: available/desired replicas, application responses, HTTP errors, merged-distribution server handling p95, and separate health-check traffic. It reuses existing metrics and scopes queries to the configured cluster/location and selected environment. Application traffic and latency exclude probes; missing/stale or sparse data is missing evidence, not success.

Use [runtime release correlation](operator-runbook.md#runtime-release-correlation) before the [read-only dashboard review](operator-runbook.md#deployment-health-dashboard-review). Health summaries do not establish provenance, verification, attestation, admission, release identity, or promotion authorization. The reviewed exact-plan apply created only the dashboard, with no changes to existing resources. Live definition and rendering were validated: the environment selector isolated dev/stage/prod, availability rendered across all three environments, dev health-check traffic was observed, and runtime release correlation remained consistent. Non-health request, p95, and error panels rendered without matching time series; their empty state is missing evidence, not proof of health or zero errors. No artificial traffic or failures were required. No alerts, SLOs, collectors, or automated decisions are added.

## Release-health alerting

One [availability alert policy](../monitoring/alert-policies/README.md) is defined declaratively for sample-service across dev/stage/prod. A single PromQL condition compares positive desired replicas with fewer available replicas for the same environment/workload, without summing collector duplicates. It evaluates every 30 seconds and requires a sustained 120-second mismatch. The reviewed exact saved-plan apply created only this enabled policy, with no changes or destruction of existing resources. Live validation confirmed the condition and timing, no notification channels or alert strategy/remediation, fresh available=1/desired=1 values across dev/stage/prod, and a non-firing condition. Cloud Monitoring showed zero firing and zero acknowledged alerts and no active alerts for this policy; the dashboard remained unchanged. No artificial failure was induced: a real FIRING lifecycle and duplicate collectors were not exercised live.

An alert requests explicit release review through [runtime correlation and dashboard inspection](operator-runbook.md#release-health-alert-review); it does not establish trust/admission or authorize promotion, rollback, or any mutation. Missing/stale telemetry or no incident is not health evidence. Combined 4xx/5xx semantics and insufficient non-health latency baseline leave error and latency alerts deferred. No notification routing, SLOs, collectors, or automated decisions are introduced.

## Release review

The [canonical release review checkpoint](operator-runbook.md#release-review-checkpoint) combines identity, trust, deployment, and operational evidence for one environment/window and records exactly one continue/hold/reject outcome with its reason. Missing operational evidence normally means hold; alternative evidence must explicitly satisfy the bounded review scope. Non-firing alerts alone do not prove health, and healthy runtime evidence cannot override invalid or missing trust. The decision executes no promotion, rollback, or other mutation.

The [manual rejection and rollback workflow](operator-runbook.md#manual-release-rejection-and-rollback) uses these observations to record rejection evidence and post-rollback health. Alerts never execute rollback. Candidate trust, historical acceptance, retained artifact protection, and separate authorization remain independent prerequisites.

## Planned signals

- Deployment availability and rollout failures.
- Request errors/latency after deployment.
- Admission denials and application error bursts.
- Dashboards for source/build/digest/verification lookup; read-only lookup already exists.

Signals support explicit operator review rather than replacing trust/admission. Alert-driven promotion and automatic rollback are not current controls.

## Release correlation and directory guidance

Use [canonical annotations](architecture/release-model.md#annotation-mapping). They identify workloads but establish neither cryptographic trust nor durable audit storage; compare with running digest and release/rollout state.

The [dashboard definition](../monitoring/dashboards/README.md) is deployed and live-validated; the [availability alert policy](../monitoring/alert-policies/README.md) is deployed and live-validated in its healthy state; [metric definitions](../monitoring/log-based-metrics/README.md) are declarative and were live-validated in dev. Keep visibility small and tied to release review. Current checks belong in [Operator Runbook](operator-runbook.md#runtime-validation); health evidence never automatically authorizes deployment.
