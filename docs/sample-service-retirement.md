# Sample-service retirement

Online Shop is the active Secure Delivery Platform workload. The initial test
sample-service is retired; restoration, preservation and sample health checks
are no longer delivery, recovery, incident-exercise or roadmap gates.

## Proposed removal

The complete refreshed foundation plan must contain only these sample-only deletes:

- `google_cloudbuild_trigger.sample_service_image`
- `google_clouddeploy_delivery_pipeline.sample_service`
- `google_clouddeploy_target.environment["stage"]` and `["prod"]`
- `google_logging_metric.sample_service_requests`, `.sample_service_errors`, `.sample_service_latency`
- `google_monitoring_dashboard.sample_service_health`
- `google_monitoring_alert_policy.sample_service_availability`

Deleting these resources ends sample delivery and monitoring. Historical cloud
release records, if any, need private export before separately authorized deletion;
do not force-delete a pipeline with unexpected releases. Retained historical
time series are not a current health claim. No apply is authorized by this document.

## Retained dependencies

Online Shop's `catalog-dev` pipeline uses the existing `environment["dev"]`
target and shared render/source bucket. Keep that target at its current identity
and configuration, including its legacy descriptive text, to avoid an unrelated
update. Stage/prod namespaces remain shared infrastructure, although their
sample-only Cloud Deploy targets are removed. New Shop promotion targets need
their own reviewed contract.

Keep both node pools and the cluster, persisted capacity mode, networking,
registry/images, build/deploy/node/reviewer/signing/telemetry identities and IAM,
KMS/note/attestor/Binary Authorization, source/candidate holds, GitHub connection,
Online Shop dashboards, endpoint, synthetic resources and their dedicated identities.
No identity or trust resource is exclusively owned by sample-service in this change.

`deploy/environments.json` remains the immutable producer binding used by Online
Shop. `deploy/deploy-release.py` retains shared metadata validation only;
`deploy/clouddeploy/release-preflight.py` retains read-only evidence evaluation
and time/protection helpers imported by Online Shop. Sample manifests, rendering,
direct deployment execution, trigger config and implementation-specific tests are removed.
Changing reviewed helper bytes requires a newly reviewed deployment revision for
future preparation; existing producer/deployment revisions and candidates are not relabeled.

## Evidence and review gates

Previously published [sample narratives](historical/sample-service/README.md)
and recorded validation JSON are historical only. Original result fields remain
unchanged; historical notices supersede old sample restoration notes. Existing
raw evidence remains in ignored private storage. New raw inventories, state,
plans, logs, hashes and the operator review report must stay private.

Use the approved isolated generated foundation root, current feature composition,
existing backend/default workspace and unchanged private inputs. Keep capacity
`paused`. Run full refresh and normal locking; no targeting, refresh bypass,
state migration, state removal, cloud mutation or Kubernetes API is needed.
Require exactly the nine confirmed deletes, zero create/update/import/replace,
and no pool, Shop or shared dependency changes. Fresh read-only inventories must
confirm target usage and paused MIG sizes. Stop review on any other planned action.
Worker-dependent readiness, smoke traffic and telemetry acceptance remain
unavailable while paused and must not be reported as passed.
