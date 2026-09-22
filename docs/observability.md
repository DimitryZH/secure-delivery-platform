# Observability

## Objective

Make release behavior visible after deployment.

This project uses Google Cloud Operations concepts to support operator review and release confidence.

## Observability goals

### 1. Release visibility
Operators should be able to answer:
- what version was deployed
- where it was deployed
- when it was promoted
- whether it is behaving normally

### 2. Post-deployment confidence
A secure release path is stronger when release health can be assessed after rollout.

### 3. Promotion support
Signals from logs, metrics, and dashboards should support promotion decisions.

## Recommended observability components

- Cloud Monitoring dashboards
- Cloud Logging views
- release-related log filters
- alert policies tied to application health

## Runtime release correlation

The base deployment manifest carries release metadata annotations on the pod template so operators can connect a running workload back to the verified release candidate.

Minimum runtime metadata to review:
- `release.secure-delivery.dev/commit-sha`
- `release.secure-delivery.dev/build-id`
- `release.secure-delivery.dev/image-digest`
- `release.secure-delivery.dev/verification-status`

These annotations should help answer what source revision, build execution, immutable artifact, and verification result produced the workload currently running in a namespace. They are not a replacement for long-term audit storage or a release catalog in the MVP.

## MVP review loop references

The monitoring notes are split by signal type so the MVP review loop stays small and easy to evolve:
- [Dashboards](../monitoring/dashboards/README.md) summarize deployment health, error rate, latency, and release metadata lookup.
- [Log-based Metrics](../monitoring/log-based-metrics/README.md) capture release events, deployment denials, and error bursts.
- [Alert Policies](../monitoring/alert-policies/README.md) identify unhealthy rollout signals that should stop or delay promotion.

Together, these notes define the first operator review loop: identify the running release, inspect health signals, review failures or denials, and decide whether promotion should continue.

## Recommended operator questions

- Did deployment succeed technically?
- Is the application healthy after rollout?
- Are there errors or latency spikes?
- Should promotion continue?
