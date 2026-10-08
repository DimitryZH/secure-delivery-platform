# Release-health Alerting

One [Terraform policy](../../terraform/foundation/alert-policy.tf.json), **Sample service deployment availability review**, defines a single PromQL condition using existing GKE deployment-state gauges. Live policy creation and incident inspection remain pending a separately reviewed plan and explicit apply authorization. Repository tests and read-only query validation do not create a policy or demonstrate an incident.

## Condition and identity

The condition is `desired replicas > 0 AND available replicas < desired replicas` for the same configured project, location, cluster, namespace, and deployment `sample-service`. The query uses the live-confirmed PromQL names `kube_deployment_status_replicas_available` and `kube_deployment_spec_replicas` for the existing `prometheus.googleapis.com/.../gauge` metrics. It restricts namespace to dev/stage/prod.

MIN available and MAX desired deduplicate `instance`/`job` collector series, grouping by `project_id, location, cluster, namespace, deployment`. Both comparisons explicitly match on those labels; the result retains environment identity. No collectors are summed. Disagreeing collectors conservatively request review; inspect raw series rather than treating aggregation as reconciliation. Currently one series per metric/environment was observed; repeat-collector handling is a query contract, not a claim that duplicate collectors were live-tested.

The single PromQL condition directly compares both gauges; an ordinary numeric threshold cannot express this changing desired count without a ratio or multiple conditions. PromQL avoids ambiguous cross-condition matching and needs no new metric. The comparison is a filtering expression without `bool`: healthy environments return no alert vector, rather than a zero-valued vector that still exists. Desired zero is excluded and is not healthy-service evidence.

Evaluation runs every 30 seconds with a 120-second duration. Read-only observations showed 30-second gauge samples; two minutes requires sustained mismatch across several evaluations instead of one transient scrape. This is a release-review delay, not an SLO. No custom auto-close strategy, remediation, notification channel, or external routing is configured. Inspect policy and incidents directly in Cloud Monitoring after authorized creation. See [PromQL policies](https://docs.cloud.google.com/monitoring/promql/create-promql-alerts).

## Read-only inspection and limitations

Use the [alert review procedure](../../docs/operator-runbook.md#release-health-alert-review). Query the existing Prometheus API with the exact checked-in expression after resolving project/location/cluster inputs privately. Preserve the namespace scope and join labels. Compare the two component vectors with fresh Kubernetes desired/available replicas for each environment. A successful empty alert vector is non-alerting only when fresh component evidence is present; missing vectors cannot prove health.

PromQL instant selectors can reuse recent samples within the service lookback window. Ingestion delay, stale data, missing collectors, or a missing gauge can delay or suppress a result. This policy does not implement telemetry-absence alerting. Inspect timestamps and readiness; do not fill missing availability with zero or infer success from no incident. An incident does not identify an immutable release; correlate current workload/release separately, especially across rollout windows. No failure injection or real FIRING incident is required for repository validation.

Error alerting is deferred: `sample_service_errors` combines HTTP 4xx and 5xx, and no traffic baseline justifies a threshold. It cannot be treated as 5xx-only server failure. Latency alerting is deferred: non-health distribution samples are absent/sparse and there is no evidence-based latency target. Keep both as dashboard/review evidence; no arbitrary thresholds, SLOs, metrics, labels, or instrumentation are added.

An operational condition requests review: identify environment, run runtime release correlation, inspect the deployment health dashboard, then explicitly decide continue/hold/reject. Neither a firing alert nor its absence establishes provenance, verification, attestation, Binary Authorization admission, Cloud Deploy release identity, or promotion authorization. No automatic approval, rejection, promotion denial, rollback, redeployment, or trust-state mutation is introduced.
