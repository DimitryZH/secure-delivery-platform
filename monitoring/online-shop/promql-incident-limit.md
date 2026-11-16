# Historical frontend-alert PromQL reconstruction

Read-only review of the one recorded [incident exercise](incident-acceptance.md); no repeated
incident, synthetic invocation or application traffic. This describes retained evidence,
not current application health or a successful historical alert-query reproduction.

## Exact query and selection

The exact resolved query was read from the recorded frontend alert policy and replayed
unchanged. Its canonical template is [frontend-errors.promql.tftpl](frontend-errors.promql.tftpl):
`sum by(service_name,deployment_environment_name,service_version,release_set_id)
(rate(<frontend non-health non-ok server requests>[5m])) > 0`.
The literal resolved query and full label/resource set are retained privately. Project,
cluster and location are resolved from the reviewed active binding, not another environment.

Metric: `workload.googleapis.com/online_shop.transport.requests`, CUMULATIVE/INT64,
resource `k8s_cluster`. Selected labels: service_name=frontend, service_namespace=online-shop,
deployment_environment_name=dev, kind=server, operation=`GET /`, outcome=`http_5xx`,
service_version=`67b6cd85ae01c698bbf86904d953d5145b7b5820` and release_set_id
`sha256:f8b585b4334eddb2a7e4962ca54bfbdbc7fb96e7751083c57d3d3924f7459f25`.
The individual Pod/instrumentation/digest labels remain in the raw series; they were not
rewritten or merged to manufacture a zero baseline. Health RPCs and `/_healthz` are excluded.

## UTC window and observed points

| Read-only observation | Result |
| --- | --- |
| Original exact query, 2026-11-16 02:23:45–02:34:00 UTC, step 15s | Empty result; reproduced unchanged |
| Same exact query, step 30s | Empty result |
| Same expression with only final `>0` removed, step 15s | One attributed series,32 samples, all rate=0 |
| Raw series, 02:15:00–02:40:00 UTC |84 points, all cumulative value 1; no earlier zero sample in this captured interval |
| First retained error-series point |02:26:09.439269 UTC, value 1 |
| Last point in the expanded interval |02:39:59.439495 UTC, value 1 |
| Full cumulative-start-to-02:40 query | The same 84 points, all 1; no preceding zero sample |
| Cumulative interval startTime |2026-11-15 20:40:39.438857 UTC; not an observed zero point |

Thus the current replay's empty vector is explained by a **zero reconstructed rate filtered
by `>0`**, despite a nonzero raw error counter. The first recorded value is already1; the
retained constant series cannot supply its initial0->1 sample transition. A cumulative
startTime does not create a real earlier zero sample. This establishes why the retained
query replay is empty; it does not establish how the live alert evaluator handled its first
observation. No evaluator implementation defect, export loss or precise streaming-versus-
retrospective mechanism is claimed without additional evidence.

## Explicit proposed disposition

Accept this as a bounded historical reconstruction limit **subject to final review**:
actual frontend incident OPEN 02:27:47/CLOSED 02:32:09, positive raw counter, native frontend
HTTP 500/GetCart Unavailable, synthetic failure/email and subsequent successful recovery remain
independent evidence. Do not label the historical query check passed or infer zero errors.
Do not change production queries, backfill fake zero points, enlarge traffic or repeat the
incident merely to obtain a chart. The six dashboard queries and the selected alert remain
unchanged. An additional failure requires its own justified scope/authorization.

The unresolved part is reconstruction of the original positive live evaluation from the
retained samples; it is not a missing-metric or healthy-zero observation. The proposed limit
must be explicitly accepted or investigated in [release review#133](https://github.com/DimitryZH/secure-delivery-platform/issues/133).
This document does not close Milestone 8 or publishv0.2.0.
