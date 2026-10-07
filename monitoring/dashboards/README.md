# Deployment Health Dashboard

One [Terraform resource](../../terraform/foundation/dashboard.tf) renders the [JSON template](sample-service-health.json.tftpl) as **Sample service deployment health**. The dashboard is deployed through the reviewed exact-plan apply, which created only this resource and changed no existing resources. The live definition matched the reviewed template. Manual rendering and single-environment selection were validated for dev/stage/prod without environment mixing; availability rendered across all three environments and health-check responses rendered in dev. Non-health request, p95, and HTTP error panels rendered correctly but had no matching time series in the inspected windows. No p95 value was displayed; it depends on non-health latency samples. Empty panels remain missing evidence, not proof of health or zero errors. No artificial traffic or failures were generated.

Run [runtime release correlation](../../docs/operator-runbook.md#runtime-release-correlation) first, then use the [dashboard review procedure](../../docs/operator-runbook.md#deployment-health-dashboard-review). The dashboard summarizes sample-service health in the configured project, cluster, and location; it does not encode immutable release identity.

## Environment and signals

A single `VALUE_ONLY` variable named `environment` offers dev/stage/prod, defaults to dev, and uses single-value selection. Monitoring substitutes its value into `monitoring.regex.full_match` for the different namespace labels and application environment label. Static namespace allowlists also limit queries to these three environments, including if a console wildcard is selected. Keep one environment selected for release review; grouped namespace/environment series prevent cross-environment merging. No release/build/commit/digest/Pod variables are added. See [dashboard variable syntax](https://docs.cloud.google.com/monitoring/dashboards/api-dashboard).

| Widget | Metric and selection | Alignment and reduction |
| --- | --- | --- |
| Deployment availability | Existing available and desired deployment replica gauges; `prometheus_target`, selected namespace, `deployment=sample-service` | Available: ALIGN_MIN then REDUCE_MIN; desired: ALIGN_MAX then REDUCE_MAX, grouped by namespace |
| Application responses | `sample_service_requests`, `k8s_container`, container sample-service, `health_check=false` | ALIGN_SUM then REDUCE_SUM across Pods, grouped by namespace/environment |
| HTTP 4xx/5xx responses | `sample_service_errors`, same application resource scope, both health classifications | ALIGN_SUM then REDUCE_SUM across Pods and health classifications, grouped by namespace/environment |
| Server handling p95 | `sample_service_latency_ms`, same application scope, `health_check=false` | ALIGN_SUM merges distributions within each resource; REDUCE_SUM merges resource distributions; secondary ALIGN_PERCENTILE_95 estimates p95 of the merged distribution |
| Health-check responses | `sample_service_requests`, same application scope, `health_check=true` | ALIGN_SUM then REDUCE_SUM across Pods, grouped by namespace/environment |

All alignments start at 60 seconds. Wider observation windows can increase chart alignment; counters show counts per aligned interval, not rates or whole-window totals. No zero filling, success thresholds, alert policies, or SLOs are configured.

Availability uses conservative interval extrema and never sums repeated collectors for one Deployment. A transition within an interval or disagreeing collectors can produce available < desired; inspect raw recent series and Kubernetes observed generation/readiness before interpreting it. Equal positive counts alone are insufficient if samples are stale. Desired zero is not application availability evidence.

Latency merges bucket counts before percentile estimation, never averages per-Pod percentiles. It measures server handling duration, not client latency. Histogram boundaries limit percentile resolution, and low sample counts or extraction gaps limit interpretation. Compare latency sample counts with request counts using the canonical metric inspection procedure. See [distribution percentiles](https://docs.cloud.google.com/monitoring/api/v3/distribution-metrics) and [aggregation API](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v1/projects.dashboards).

## Limitations and trust boundary

Existing dev samples demonstrated health_check=true ingestion; health_check=false was absent in the accepted baseline window. Primary application traffic and latency charts can therefore be empty. The error chart can be empty when no matching 4xx/5xx responses occur; absence is not proof of zero errors. Do not generate traffic or artificial failures to populate panels. Missing/stale series are missing evidence, not success. Metrics are forward-looking and ingestion can lag.

Pod resource labels still contribute ingestion cardinality and cost; chart aggregation does not reduce them. Windows spanning multiple releases mix their operational behavior. Recheck runtime identity after review and keep project-specific evidence private.

Dashboard health is operational evidence only. It establishes neither provenance, verification, attestation validity, Binary Authorization admission, Cloud Deploy release identity, nor promotion authorization. Continue/hold/reject review remains explicit; a healthy dashboard never automatically authorizes promotion. No generic infrastructure views, new metrics, collectors, backend, alerts, SLOs, tracing, or automated decisions are introduced.
