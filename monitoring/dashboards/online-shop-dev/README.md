# Online Shop dev observability

The [Cloud Monitoring dashboard](dashboard.json.tftpl) uses six PromQL queries and is managed by [foundation Terraform](../../../terraform/foundation/dashboard.tf). The review targets the running Online Shop in `dev` on rollout `dev-full-003`. See [read-only validation](validation.json) for the checked windows and attribution.

## Ingestion and ownership

| Selected metrics | Single ingestion path | Storage and resource |
| --- | --- | --- |
| `online_shop.transport.requests` and `online_shop.transport.duration` | Ten application services send OTLP to `catalog-collector.dev.svc.cluster.local:4317`. The `catalog-collector` DaemonSet selects each service into its own metrics pipeline and exports through `googlecloud` using the existing `dev/catalog-collector` Workload Identity. | `workload.googleapis.com` in Cloud Monitoring (Monarch), resource `k8s_cluster`. Request counts are cumulative INT64 and durations are cumulative distributions in seconds. |
| `kube_deployment_status_replicas_available` and `kube_deployment_spec_replicas` | GKE managed collection scrapes the existing `kube-state-metrics` target. | `prometheus.googleapis.com` in Cloud Monitoring (Monarch), resource `prometheus_target`. These are Kubernetes gauges. |

The Online Shop deployment owns application instrumentation and Collector pipelines; the platform foundation owns the Collector export identity and GKE managed collection. Both namespaces are available through the same [Cloud Monitoring PromQL API](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus/query-api-ui). GKE managed collection already handles platform series. It has no `PodMonitoring` for Shop in `dev`; the two observed `ClusterPodMonitoring` resources select kube-state-metrics and the GKE DCGM exporter. The application Collector has no Prometheus receiver or exporter. There is no need for a second Shop ingestion path, scrape resource, remote write, or recording rule. `online_shop.transport.errors` is a separate, sparse counter on the same OTLP route. The error panel derives its numerator from request outcomes so the numerator and denominator use the same population. The existing Redis singleton exports `workload.googleapis.com/redis.commands` (a gauge in operations per second) through `googlecloud` and remains separate from application request panels.

## Queries and interpretation

Terraform substitutes the configured project, cluster and location in each query. Use the same rendered PromQL in Metrics Explorer or in the Prometheus `query` and `query_range` APIs. The application charts group by `service_name`, `deployment_environment_name`, `service_version`, and `release_set_id`. Pods and operations are aggregated within each group. Use the legend to isolate a service and release.

| Panel | Query | Reading |
| --- | --- | --- |
| Application requests | [request-rate](queries/request-rate.promql.tftpl) | Average completed server operations per second over 15 minutes. Zero is possible for a present, unchanged counter; a missing counter leaves a gap. |
| Application errors | [error-rate](queries/error-rate.promql.tftpl) | Non-`ok` server outcomes per second. Zero is shown only when the same attributed group has observed requests and no observed errors. |
| Server latency p95 | [p95-latency](queries/p95-latency.promql.tftpl) | Estimated p95 in seconds from the pooled histogram buckets per group over 15 minutes. A positive histogram observation rate is required. |
| Observed server success | [observed-availability](queries/observed-availability.promql.tftpl) | Percentage of observed server outcomes marked `ok`. An all-error window reports 0%; a window without observed requests leaves a gap. This is an application signal, not endpoint uptime or a time-based SLO. |
| Kubernetes readiness | [available-replicas](queries/available-replicas.promql.tftpl), [desired-replicas](queries/desired-replicas.promql.tftpl) | Compare the available and desired replica counts for each of the ten deployments. These cluster gauges have namespace/deployment attribution and carry no application version or release labels. |

Application queries use `kind="server"` and exclude `/_healthz` and standard gRPC health operations. The frontend also bypasses application instrumentation for its health endpoint. Health probes are outside these traffic panels; replica readiness is separate and does not count probe calls. Per-service traffic includes downstream server operations and can include nonhuman callers. The app treats HTTP responses below 500 as `ok`; gRPC uses its own status outcomes. Cloud Armor denials and connection failures that do not reach the application are outside these metrics. See [PromQL metric naming and histogram suffixes](https://docs.cloud.google.com/monitoring/promql).

## From a checkout to its trace and logs

Use the dashboard's UTC window, service, version and release to locate the signal. Metrics aggregate observations across requests, so use the checkout trace ID from the private journey record or a native Cloud Logging entry to identify the individual request.

1. Open the trace in Cloud Trace in the monitored project. Find frontend `POST /cart/checkout`, check its HTTP response and follow downstream spans. Compare span service, environment, version, release and component digest to the accepted release.
2. In Logs Explorer set the same UTC window and use the filter below. Add `labels."service.name"="frontend"` and the matching `labels.component_digest` to narrow to one component. Compare the native `spanId` with the selected trace span. Use application completion events for each component, as defined in [complete application signals acceptance](../../../deploy/online-shop/complete-README.md).

```text
log_id("online-shop/catalog")
resource.labels.namespace_name="dev"
trace="projects/PROJECT_ID/traces/TRACE_ID"
labels."deployment.environment.name"="dev"
labels."service.version"="SERVICE_VERSION"
labels.release_set_id="RELEASE_SET_ID"
(jsonPayload.event="request.completed" OR jsonPayload.event="operation.completed")
```

## Plan for live acceptance after review

1. Review a full foundation Terraform plan with existing backend/workspace and operator inputs. Preserve `-var=shop_edge_enforce_evaluated_rules=true` as documented in the [endpoint enforcement procedure](../../../deploy/online-shop/endpoint-README.md). Expect one new resource, `google_monitoring_dashboard.online_shop_dev`; stop if the plan changes collection, IAM, workloads, the endpoint, or another dashboard. Apply only after approval and compare the live dashboard definition to the reviewed render.
2. Record the active dev rollout, accepted release and component digests, and a pre-journey UTC baseline. Check that sample-service is Ready/Available and responds HTTP 200 in dev/stage/prod. Query both the app and readiness charts.
3. Run the [existing protected endpoint procedure](../../../deploy/online-shop/endpoint-README.md) once against `https://shop.runtimeplatforms.dev` using `complete-acceptance.py endpoint-journey`, one private output directory and fictional checkout details. Confirm browse, cart, checkout and order confirmation within the existing 20-request cap. Preserve the recorded UTC window and trace ID.
4. Clean up after the attempt, even if telemetry or checkout verification fails. Confirm the loopback port-forward targets the verified dev `redis-cart` Service endpoint and use the [scoped cleanup](../../../deploy/online-shop/complete-README.md) with the private session record. Send only `DEL` and `EXISTS` for that exact key, require `EXISTS=0`, and stop the owned forward. Recheck sample-service dev/stage/prod.
5. After telemetry arrives, compare the dashboard and Prometheus API for that window. Verify frontend checkout telemetry and downstream activity for the expected release, use trace/span IDs to find native-linked completion logs, and verify that health probes do not enter the application traffic panels. Check the difference between zero errors with traffic and gaps without usable data. Use the retained historical error observation to check the positive error path without injecting a new failure. Keep raw responses, trace IDs, session data and cleanup readbacks private. Publish only sanitized results.

Dashboard publication and this fresh checkout are pending review. Alert policies, scheduled synthetic checks and failure exercises are outside this change.
