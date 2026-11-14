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
Shop. `deploy/deploy-release.py` is retained **unchanged as a legacy dependency**:
its exact historical bytes participate in the shared producing trust-file set.
The shared read-only `deploy/clouddeploy/release-preflight.py` imports it, and
Online Shop imports the preflight time/protection helpers. Do not exclude the
legacy helper from trust checks or change its bytes to retire sample execution:
a different deployment SHA cannot make changed shared producing files compatible
with an existing candidate's immutable producing revision. The old sample CLI
is unsupported; its manifests, example, bundle generator, image-build config and
trigger are removed. Do not invoke it to restore or deploy sample-service.

The regression replays real historical Git blobs with distinct producing and
deployment revisions. It confirms reuse with the unchanged helper and confirms
`incompatible_producing_trust_files` for the changed helper from the initial
retirement commit, even after a separate deployment review. Producing identities,
accepted candidates and the complete trust-file checks remain unchanged.

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
