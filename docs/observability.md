# Observability

## Current validation and planned visibility

Current delivery supplies annotations, rollout/job results, readiness, digest inspection, and manual internal HTTP checks. Platform Logging/Monitoring access does not imply application dashboards, metrics, alerts, or automated release decisions exist.

Operational Visibility remains an architectural capability in the [Roadmap](roadmap.md), answering what runs, where, when it changed, and whether it behaves normally.

## Planned signals

- Deployment availability and rollout failures.
- Request errors/latency after deployment.
- Admission denials and application error bursts.
- Source/build/digest/verification lookup.

Signals support explicit operator review rather than replacing trust/admission. Alert-driven promotion and automatic rollback are not current controls.

## Release correlation and directory guidance

Use [canonical annotations](architecture/release-model.md#annotation-mapping). They identify workloads but establish neither cryptographic trust nor durable audit storage; compare with running digest and release/rollout state.

Existing [dashboard](../monitoring/dashboards/README.md), [metric](../monitoring/log-based-metrics/README.md), and [alert](../monitoring/alert-policies/README.md) notes describe planned assets. Keep visibility small and tied to release review. Current checks belong in [Operator Runbook](operator-runbook.md#runtime-validation); health evidence never automatically authorizes deployment.
