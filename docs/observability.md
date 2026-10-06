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

## Planned signals

- Deployment availability and rollout failures.
- Request errors/latency after deployment.
- Admission denials and application error bursts.
- Dashboards for source/build/digest/verification lookup; read-only lookup already exists.

Signals support explicit operator review rather than replacing trust/admission. Alert-driven promotion and automatic rollback are not current controls.

## Release correlation and directory guidance

Use [canonical annotations](architecture/release-model.md#annotation-mapping). They identify workloads but establish neither cryptographic trust nor durable audit storage; compare with running digest and release/rollout state.

Existing [dashboard](../monitoring/dashboards/README.md), [metric](../monitoring/log-based-metrics/README.md), and [alert](../monitoring/alert-policies/README.md) notes describe planned assets. Keep visibility small and tied to release review. Current checks belong in [Operator Runbook](operator-runbook.md#runtime-validation); health evidence never automatically authorizes deployment.
