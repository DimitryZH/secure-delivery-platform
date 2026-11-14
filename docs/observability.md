# Observability

Online Shop uses the existing independently trusted Collector, native trace/log
linkage and [six-query dashboard](../monitoring/dashboards/online-shop-dev/README.md).
[Scheduled monitoring](../monitoring/online-shop/README.md) and the
[incident procedure](../monitoring/online-shop/incident-runbook.md) have separate
provisioning, scheduling and live acceptance gates.

Sample request/error/latency metrics, dashboard and availability alert are retired;
their earlier validation is [historical](historical/sample-service/README.md).
No sample restoration or smoke check is required for Online Shop.

Keep source/version/release attribution, bounded traffic/session cleanup and probe
exclusion. Missing or stale telemetry is missing evidence, not zero errors.
Paused workers cannot provide current runtime or telemetry acceptance.
The [release review](operator-runbook.md#release-review-checkpoint) and
[manual rejection and rollback](operator-runbook.md#manual-release-rejection-and-rollback)
remain separate from execution authorization. Alerts never execute rollback.
