# Operator Runbook

## Preconditions and authorization

Use reviewed immutable configuration and a real verified/attested candidate. Synthetic records are offline fixtures, never live evidence. Replace placeholders privately. Review [Release Model](architecture/release-model.md), [IAM Model](iam-model.md), and [artifact protection](trusted-delivery.md#source-and-rendered-artifact-protection).

Before mutations read-only verify exact digest, source/build/trust correlation, cryptographic attestation, live target/release snapshot approvals, prior rollout success, artifact hashes/availability, sufficient retention, unchanged IAM/admission, and no unexpected workload replacement. Stop on mismatch. Do not create a replacement release or expand IAM to recover.

## Attestation inspection

Use reviewed scripts/settings with `cloudbuild/scripts/attest-release.py --inspect-only`. Supply metadata, approved registry, project, attestor, note, bare KMS key resource (`--key-version`), and matching canonical URI (`--public-key-id`). Require subject/note/key equality and signature validation. This does not sign or write. Signing submission requires separately reviewed source, source-upload/build-submission permissions, and signer `actAs`.

```sh
python cloudbuild/scripts/attest-release.py \
  --metadata /local/release-metadata.json \
  --approved-registry us-central1-docker.pkg.dev/<PROJECT_ID>/secure-delivery \
  --project <PROJECT_ID> --attestor <ATTESTOR> \
  --note projects/<PROJECT_ID>/notes/<NOTE> \
  --key-version projects/<PROJECT_ID>/locations/<REGION>/keyRings/<KEY_RING>/cryptoKeys/<KEY>/cryptoKeyVersions/<VERSION> \
  --public-key-id //cloudkms.googleapis.com/v1/projects/<PROJECT_ID>/locations/<REGION>/keyRings/<KEY_RING>/cryptoKeys/<KEY>/cryptoKeyVersions/<VERSION> \
  --inspect-only
```

For a separately authorized signing operation, submit only the reviewed signing bundle with candidate `release-metadata.json`:

```sh
gcloud builds submit <TRUSTED_SOURCE_DIRECTORY> \
  --project=<PROJECT_ID> --region=us-central1 \
  --config=cloudbuild/cloudbuild-attest.yaml \
  --gcs-source-staging-dir=gs://<ATTESTATION_SOURCE_BUCKET>/source \
  --substitutions=_LOCATION=us-central1,_REPOSITORY=secure-delivery
```

Inspection is read-only; submission signs and writes an occurrence. Never substitute candidate-controlled configuration or execute submission as an inspection step.

## Release preparation and creation

Prepare locally using `deploy/clouddeploy/prepare-release.py`; inspect all target views. Record immutable configuration, metadata SHA-256, and deterministic archive SHA-256. Upload a unique source object under `gs://<CLOUD_DEPLOY_BUCKET>/source/<RELEASE_NAME>/` with a create-only generation precondition. Upload and release creation are separately authorized mutations.

Verify uploaded bytes/hash, generation, retention expiration, bucket ownership/location. After creation verify the actual release source URI/object again. Release annotations correlate full commit, image build ID, digest, trust reference, verification timestamp, archive SHA-256, and metadata SHA-256.

```sh
gcloud deploy releases create <RELEASE_NAME> \
  --project=<PROJECT_ID> --region=us-central1 \
  --delivery-pipeline=sample-service \
  --source=gs://<CLOUD_DEPLOY_BUCKET>/source/<RELEASE_NAME>/<UNIQUE_ARCHIVE>.tar.gz \
  --gcs-source-staging-dir=gs://<CLOUD_DEPLOY_BUCKET>/source/<RELEASE_NAME> \
  --skaffold-file=skaffold.yaml --disable-initial-rollout \
  --annotations=<REVIEWED_RELEASE_ANNOTATIONS>
```

Templates are not authorization. No image overrides. Require successful render, all target namespaces/digests/annotations, and no hooks/build/bypass. Render failure stops; corrective mutations need new authorization.

## Initial dev rollout

After fresh preflight and separate authorization, create only dev for the existing release. Require no existing rollout or unexpected workload replacement.

```sh
gcloud deploy rollouts create <DEV_ROLLOUT_ID> \
  --project=<PROJECT_ID> --region=us-central1 \
  --delivery-pipeline=sample-service --release=<RELEASE_NAME> --to-target=dev
```

Wait for terminal success and runtime validation before considering stage.

## Controlled promotion

Promotion and approval are separate mutations. Confirm successful prior environment, absent next rollout, live/snapshot approval settings, exact identity, available/hash-matching artifacts, and unchanged IAM/admission. Reserve deployment time plus validation margin; the validated gate used at least 75 minutes of protection.

After separate promotion authorization:

```sh
gcloud deploy releases promote --release=<RELEASE_NAME> \
  --project=<PROJECT_ID> --region=us-central1 \
  --delivery-pipeline=sample-service --to-target=<TARGET> --rollout-id=<ROLLOUT_ID>
```

For stage/prod require `PENDING_APPROVAL`, `approvalState=NEEDS_APPROVAL`, no deployment yet, unchanged previous workloads, and no next-target workload. Stop and obtain separate approval authorization. Repeat preflight/protection checks immediately before approval.

Only after separate authorization:

```sh
gcloud deploy rollouts approve <ROLLOUT_ID> \
  --project=<PROJECT_ID> --region=us-central1 \
  --delivery-pipeline=sample-service --release=<RELEASE_NAME>
```

Wait for terminal rollout/job results. Failure means stop, not automatic rollback/correction. See [Controlled Promotion Validation](trusted-delivery.md#controlled-promotion-validation) for screenshots.

## Runtime release correlation

This read-only procedure answers what runs in a namespace and which release/rollout it correlates with. It uses the [canonical annotation mapping](architecture/release-model.md#annotation-mapping); it does not add metadata or establish cryptographic trust. Run it separately for dev, stage, and prod. Commands below use a POSIX shell, gcloud, and kubectl with existing read permissions. Stop on any command failure or failed comparison; these are manual review commands, not an automated pass/fail helper. Keep raw output private: it contains project, identity, and cluster details. Public examples must use placeholders.

### 1. Confirm the observation boundary

Supply the expected values from reviewed environment configuration, not from an unverified workload. Use an already configured, explicitly selected context. Do not rely on the current context, obtain deployment credentials, or change IAM to make inspection work. If the expected context or read permission is unavailable, stop; a separately configured read-only client can perform the same GET requests.

```sh
PROJECT_ID='<PROJECT_ID>'
REGION='<REGION>'
ZONE='<ZONE>'
CLUSTER='<GKE_CLUSTER>'
CONTEXT='<EXPECTED_CONTEXT>'
ENVIRONMENT='dev'  # Repeat with stage and prod.
PIPELINE='sample-service'

gcloud container clusters describe "$CLUSTER" \
  --project="$PROJECT_ID" --location="$ZONE" \
  --format='json(name,location,endpoint,privateClusterConfig.privateEndpoint,privateClusterConfig.publicEndpoint,controlPlaneEndpointsConfig)'
kubectl --context="$CONTEXT" config view --minify \
  -o 'jsonpath={.clusters[0].cluster.server}{"\n"}'
kubectl --context="$CONTEXT" --request-timeout=30s get namespace "$ENVIRONMENT" \
  -o 'jsonpath={.metadata.name}{"\n"}'
```

Require the namespace to equal the selected environment and the context server to identify the reviewed cluster endpoint (including the selected private or DNS endpoint, when applicable). An unrelated context is inconsistent evidence, even if it has a namespace with the same name. Never print `config view --raw`, tokens, or kubeconfig contents.

### 2. Inspect the Deployment and its actual Pods

```sh
kubectl --context="$CONTEXT" --request-timeout=30s --namespace="$ENVIRONMENT" \
  get deployment sample-service -o json
kubectl --context="$CONTEXT" --request-timeout=30s --namespace="$ENVIRONMENT" \
  get replicasets --selector=app=sample-service -o json
kubectl --context="$CONTEXT" --request-timeout=30s --namespace="$ENVIRONMENT" \
  get pods --selector=app=sample-service -o json
```

Inspect `Deployment.spec.template.metadata.annotations`, not just top-level Deployment annotations. Require all ten canonical annotations on the template and each Pod. Compare their values exactly, including source repository, full commit SHA, producing build ID/identity, verification status/timestamp, trust reference, target environment, and deployment authority. Require `verification-status=passed`, a valid UTC verification timestamp, expected source/build/deployment identities from reviewed configuration, and a nonempty occurrence reference in the expected project. A reference must not be a synthetic fixture. These checks establish consistent claims, not signature validity or independently verified build provenance.

Follow controller `ownerReferences` by UID: each selected Pod must belong to a ReplicaSet owned by this Deployment. Labels alone are insufficient ownership evidence. Require the Deployment's current generation to be observed, all desired replicas updated/available, and the selected owned Pod count to equal the desired replica count. Require Running/Ready Pods without deletion timestamps, including ready container statuses. Zero replicas, extra/old Pods, foreign owners, or an in-progress update do not yield a settled baseline.

For the `sample-service` container, compare all of:

- Deployment template `spec.containers[].image`;
- each owned Pod's `spec.containers[].image`;
- each owned Pod's `status.containerStatuses[].imageID`;
- canonical `image-digest` on the template and Pods.

Desired images must be the expected registry/repository `sample-service@sha256:<digest>`, never tags. Runtime `imageID` must expose the same immutable digest. Strip only a known runtime scheme such as `docker-pullable://` before comparing an image reference; do not confuse `containerID` with `imageID` or accept a substring match. A bare runtime `sha256:<digest>` can confirm digest equality but does not identify a registry. Missing imageID is missing evidence; a different digest is inconsistent evidence. If a multi-platform image exposes a child manifest digest rather than the release digest, stop and investigate the manifest relationship read-only; do not silently accept it. Require `APP_ENV` and the target-environment annotation to equal the namespace. Reject unexpected containers or missing container status rather than claiming unexamined images belong to the candidate.

### 3. Locate the release from existing Cloud Deploy labels

On the Deployment, Pod template, and owned Pods, compare these existing labels exactly: `deploy.cloud.google.com/project-id`, `location`, `delivery-pipeline-id`, `release-id`, and `target-id`. They must match the reviewed project, region, pipeline, and environment. The release ID must agree across the resources. Set `RELEASE` only after these checks:

```sh
RELEASE='<RELEASE_ID_FROM_MATCHING_LABELS>'
gcloud deploy releases describe "$RELEASE" \
  --project="$PROJECT_ID" --region="$REGION" --delivery-pipeline="$PIPELINE" \
  --format='json(name,annotations,renderState,targetSnapshots,targetRenders)'
gcloud deploy targets describe "$ENVIRONMENT" \
  --project="$PROJECT_ID" --region="$REGION" \
  --format='json(Target)'
```

Require the exact release resource under the expected pipeline, `renderState=SUCCEEDED`, and `targetRenders[<ENVIRONMENT>].renderingState=SUCCEEDED`. Compare the release's canonical annotation values for source repository, commit SHA, build ID, image digest, verification timestamp, and trust reference with the runtime values. Its `release-name` annotation must equal the resource's release ID. This joins the runtime digest to the same source/build/verification/trust candidate; Kubernetes does not supply a canonical rollout annotation.

Require exactly one matching target snapshot in the release. Its GKE cluster resource must equal `projects/<PROJECT_ID>/locations/<ZONE>/clusters/<GKE_CLUSTER>`, and its DEPLOY execution identity must equal the runtime deployment-authority annotation. Compare cluster, deployment identity, and approval requirement with the current target as well (the target describe response wraps this resource in `Target`); drift is a reason to stop and review, not permission to alter the target. Use the release snapshot to understand historical execution, rather than treating current target configuration as proof of what previously ran.

### 4. Correlate the target rollout and state

```sh
gcloud deploy rollouts list --release="$RELEASE" \
  --project="$PROJECT_ID" --region="$REGION" --delivery-pipeline="$PIPELINE" \
  --format='json(name,targetId,state,approvalState,createTime,deployStartTime,deployEndTime)'
ROLLOUT='<UNAMBIGUOUS_ROLLOUT_ID_FOR_TARGET>'
gcloud deploy rollouts describe "$ROLLOUT" --release="$RELEASE" \
  --project="$PROJECT_ID" --region="$REGION" --delivery-pipeline="$PIPELINE" \
  --format='json(name,targetId,state,approvalState,deployStartTime,deployEndTime,phases)'
```

Require a rollout under this exact release with `targetId` equal to the environment, `state=SUCCEEDED`, completed deployment timestamps, and a successful deploy job in `phases`. Stage/prod must have `approvalState=APPROVED`; dev normally has `DOES_NOT_NEED_APPROVAL`. Pending, failed, or unapproved rollouts are observable states but do not satisfy the successful correlation baseline.

The baseline requires one unambiguous rollout for this release/target. If multiple attempts exist, do not select the newest or the only successful one automatically: release/target labels do not identify an individual attempt. Stop and inspect existing job runs and deployment history read-only before making an attribution. Missing Cloud Deploy labels also stop this workflow: the direct deployment consumer does not fabricate a Cloud Deploy release identity.

Repeat the Deployment and Pod reads after Cloud Deploy inspection. Require unchanged Deployment UID/generation, Pod UIDs, imageIDs, and correlation fields; if they changed, discard the mixed observation and repeat after the workload settles. Sequential reads are not an atomic historical snapshot. These resource comparisons provide operational correlation, not proof that no other deployment writer has ever modified the workload.

### 5. Record the conclusion without publishing raw evidence

Privately record observation time, environment/namespace, Deployment and owned Pods, desired/running digest, source revision/build, verification status/time, trust reference, release/target/rollout, and rollout state. Classify the result as consistent only when every comparison above passes. Otherwise distinguish:

- **Missing evidence:** absent annotation, label, imageID, release, rollout, or unavailable read access. No consistency conclusion is possible.
- **Inconsistent evidence:** present values disagree, ownership/cluster/namespace differs, verification failed, or the workload/rollout is not settled and successful. Stop without remediation.
- **Ambiguous evidence:** multiple possible rollouts or changing runtime state. Do not guess an attribution.

Do not include service-account emails, private identifiers, raw JSON, or local credential paths in public records. Report sanitized check outcomes using placeholders. Cryptographic inspection remains the separate [attestation inspection](#attestation-inspection) procedure; runtime claims do not replace it or Binary Authorization. Correlation authorizes no deployment, promotion, approval, rollback, trust-policy, admission, or IAM mutation.

## Runtime validation

Use [runtime release correlation](#runtime-release-correlation) for the identity and Cloud Deploy checks. Require rollout/deploy job `SUCCEEDED`, expected target, available Deployment, Running/Ready Pods, exact desired/running digest and imageID, preserved annotations/correlation, unchanged previous environments/IAM/admission, and no unauthorized rollout or break-glass/bypass/policy override.

Service stays ClusterIP. Use read-only internal connectivity, such as Kubernetes API service proxy, for `/healthz` and `/`: require HTTP 200, health `status=ok`, root `service=sample-service`, `status=running`, and expected environment. Never add a helper workload, LoadBalancer, or Ingress for this check.

Inspect job logs/ReplicaSet events read-only to distinguish admission rejection, scheduling, and image-pull failure. Deployment acceptance does not imply admitted Pods. Keep raw evidence private and redact before public sharing.

## Application log inspection

Run this read-only procedure only after a separately authorized trusted application version is deployed. Shell examples use a POSIX shell, as in runtime release correlation. Offline JSON tests do not prove Cloud Logging ingestion. Use existing Logging read permission; unavailable access is missing evidence, not permission to expand IAM. Keep raw query results private.

First use [runtime release correlation](#runtime-release-correlation) to identify the reviewed cluster/location, namespace, container, current owned Pod, immutable digest, release, and successful target rollout. Select an observation window after that rollout completed. Do not attribute old-version logs to the new release just because the service name matches.

Confirm existing workload collection read-only:

```sh
gcloud container clusters describe <GKE_CLUSTER> \
  --project=<PROJECT_ID> --location=<ZONE> \
  --format='json(loggingService,loggingConfig)'
```

Require Cloud Logging integration with `WORKLOADS` enabled. The managed GKE collector supplies `k8s_container` resource labels; no logging sidecar or application credentials are needed. This configuration check alone does not prove that an event was ingested or that an exclusion did not discard it.

In Logs Explorer, select the reviewed project and use the following filter, substituting the exact correlated Pod and the GKE cluster location (a zone for this cluster):

```text
resource.type="k8s_container"
resource.labels.project_id="<PROJECT_ID>"
resource.labels.location="<ZONE>"
resource.labels.cluster_name="<GKE_CLUSTER>"
resource.labels.namespace_name="<ENVIRONMENT>"
resource.labels.container_name="sample-service"
resource.labels.pod_name="<CORRELATED_POD_NAME>"
log_id("stdout")
timestamp >= "<OBSERVATION_START_UTC>"
timestamp < "<OBSERVATION_END_UTC>"
```

The same filter works with `gcloud logging read`. Store it in a shell variable without private output entering repository files:

```sh
LOG_FILTER='resource.type="k8s_container"
resource.labels.project_id="<PROJECT_ID>"
resource.labels.location="<ZONE>"
resource.labels.cluster_name="<GKE_CLUSTER>"
resource.labels.namespace_name="<ENVIRONMENT>"
resource.labels.container_name="sample-service"
resource.labels.pod_name="<CORRELATED_POD_NAME>"
log_id("stdout")
timestamp >= "<OBSERVATION_START_UTC>"
timestamp < "<OBSERVATION_END_UTC>"'

gcloud logging read "$LOG_FILTER" --project=<PROJECT_ID> --limit=50 \
  --order=asc --format='json(timestamp,severity,resource.labels,jsonPayload,textPayload)'
gcloud logging read "$LOG_FILTER AND jsonPayload.event=\"http_request\"" \
  --project=<PROJECT_ID> --limit=50 --order=asc \
  --format='json(timestamp,severity,resource.labels,jsonPayload)'
```

Require parsed `jsonPayload` request records with `service=sample-service`, environment equal to namespace, expected method/path/status, finite non-negative numeric `latency_ms`, and boolean `health_check`. `severity` is a special structured logging field: inspect the top-level LogEntry field rather than requiring `jsonPayload.severity`. Expect INFO for statuses below 400, WARNING for 4xx, and ERROR for 5xx. Startup records have `event=startup` and are not request events.

Append `AND jsonPayload.health_check=true` to inspect health traffic, or `AND jsonPayload.health_check=false` to exclude it. Append `AND severity>=ERROR` to inspect server/request errors. Append `AND jsonPayload.path="/" AND jsonPayload.status=200` to inspect successful root responses. Apply these to the request-event filter, not the startup query. No metric or alert is created by a read query.

Health probes can supply health events. For root-response validation, use the existing read-only [internal HTTP check](#runtime-validation) without creating a helper workload or ingress, and query its observation window. Allow ingestion delay and repeat the read before concluding events are missing. An empty result is missing evidence; wrong environment, unstructured request records, invalid fields, or conflicting workload identity is inconsistent evidence. A limit of 50 is a bounded sample, not a request count or an absence-of-errors guarantee.

Compare each event's project/location/cluster/namespace/Pod/container resource labels with the selected workload. Repeat runtime correlation after the query to ensure the same Pod UID, image digest, release identity, and rollout still agree. Kubernetes resource labels identify the log-producing workload, not its cryptographic trust. If the Pod has disappeared or changed, stop current-runtime attribution and inspect retained deployment history read-only; do not attach historical logs to an unrelated current Pod. Public conclusions use placeholders and sanitized check outcomes only.

## Release-health metric inspection

This is a read-only workflow. Application metrics must first exist through a separately reviewed Terraform plan and authorized apply; repository definitions do not mean they are deployed. Use existing Monitoring read permission. Missing access or collection is a reason to stop, not permission to alter IAM, enable monitoring components, or generate failures.

First perform [runtime release correlation](#runtime-release-correlation), recording the reviewed project, cluster/location, environment, Deployment, owned Pods, digest, release, and successful rollout privately. Choose a UTC observation window after the rollout and allow ingestion delay. Recheck current workload identity after metric reads; time series aggregate behavior, not immutable release identity. A window containing multiple releases cannot attribute all traffic to the newest release.

For workload availability in Metrics Explorer, select the existing `prometheus.googleapis.com/kube_deployment_status_replicas_available/gauge` and `prometheus.googleapis.com/kube_deployment_spec_replicas/gauge`. Use `prometheus_target`, project/location/cluster/namespace resource filters, and metric label `deployment=sample-service`. Compare recent available and desired values from matching timestamps. Require desired > 0 and available = desired, then check Deployment observed generation/available replicas and owned Pod readiness with [runtime validation](#runtime-validation). Missing/stale series and scale-to-zero are not success. These deployment-state metrics already exist in the reviewed GKE integration; do not enable or install a collector to recover absent data.

After authorized creation, inspect the application definitions read-only:

```sh
for METRIC_NAME in sample_service_requests sample_service_errors sample_service_latency_ms; do
  gcloud logging metrics describe "$METRIC_NAME" --project=<PROJECT_ID> \
    --format='json(name,filter,metricDescriptor,labelExtractors,valueExtractor,bucketOptions,disabled)'
done
```

Compare them with [checked-in definitions](../terraform/foundation/logging-metrics.tf.json). Require DELTA/INT64 counters, DELTA/DISTRIBUTION latency in ms, the canonical filters, two bounded labels, the numeric latency extractor, and explicit buckets. Do not change metrics from this inspection procedure.

The Monitoring time-series API supports the same scoped read in a reproducible observation window. POSIX shell example; keep response data and credentials private, and avoid shell tracing:

```sh
PROJECT_ID='<PROJECT_ID>'
ZONE='<ZONE>'
CLUSTER='<GKE_CLUSTER>'
ENVIRONMENT='<ENVIRONMENT>'
START_UTC='<OBSERVATION_START_UTC>'
END_UTC='<OBSERVATION_END_UTC>'
ACCESS_TOKEN="$(gcloud auth print-access-token)"

# Availability: repeat with kube_deployment_spec_replicas/gauge.
METRIC_TYPE='prometheus.googleapis.com/kube_deployment_status_replicas_available/gauge'
METRIC_FILTER="metric.type=\"$METRIC_TYPE\" AND resource.type=\"prometheus_target\" AND resource.labels.project_id=\"$PROJECT_ID\" AND resource.labels.location=\"$ZONE\" AND resource.labels.cluster=\"$CLUSTER\" AND resource.labels.namespace=\"$ENVIRONMENT\" AND metric.labels.deployment=\"sample-service\""
curl --fail --silent --show-error --get \
  "https://monitoring.googleapis.com/v3/projects/$PROJECT_ID/timeSeries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "filter=$METRIC_FILTER" \
  --data-urlencode "interval.startTime=$START_UTC" \
  --data-urlencode "interval.endTime=$END_UTC" \
  --data-urlencode 'view=FULL'

# Requests: repeat with sample_service_errors and sample_service_latency_ms.
METRIC_TYPE='logging.googleapis.com/user/sample_service_requests'
METRIC_FILTER="metric.type=\"$METRIC_TYPE\" AND resource.type=\"k8s_container\" AND resource.labels.project_id=\"$PROJECT_ID\" AND resource.labels.location=\"$ZONE\" AND resource.labels.cluster_name=\"$CLUSTER\" AND resource.labels.namespace_name=\"$ENVIRONMENT\" AND resource.labels.container_name=\"sample-service\" AND metric.labels.environment=\"$ENVIRONMENT\" AND metric.labels.health_check=\"false\""
curl --fail --silent --show-error --get \
  "https://monitoring.googleapis.com/v3/projects/$PROJECT_ID/timeSeries" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "filter=$METRIC_FILTER" \
  --data-urlencode "interval.startTime=$START_UTC" \
  --data-urlencode "interval.endTime=$END_UTC" \
  --data-urlencode 'view=FULL'
unset ACCESS_TOKEN
```

Follow `nextPageToken` with the same query and `pageToken` when present; a first page is not a complete count. Inspect sample timestamps, metric labels, and resource identity. For availability, repeated collector series represent the same Deployment; do not sum duplicate collectors. For request/error totals, use identical windows and health selection, align DELTA counters with SUM over a common interval (for example 60 seconds), then reduce SUM across resource series grouped by environment/health classification. RATE is requests per second, not the interval count. For latency, align and merge distributions across the same resources/window before deriving percentiles; do not average per-Pod percentile values. In Metrics Explorer choose these aligners/reducers without saving a dashboard or alert.

The example excludes health traffic. Change the health label to true to inspect probes or omit it to include both; state the choice in the review. Error metrics count 4xx and 5xx responses; absent points do not prove zero failures. Latency histogram counts can differ from request counts if extraction fails. Metrics are not retroactive and collection can lag: wait and re-read within a bounded window without restarting or redeploying. Do not generate errors just to populate a counter. Monitor actual series volume because built-in Pod resource labels still contribute cardinality and cost.

Use [application log inspection](#application-log-inspection) to inspect matching structured events and compare identity/health classification. Use runtime release correlation to connect that workload to source/build/verification/trust and Cloud Deploy state. Logs, metric health, and resource labels are operational evidence, not cryptographic trust, admission proof, or deployment authorization. Dashboards, alerts, SLOs, and automatic decisions remain outside this procedure.

## Deployment health dashboard review

This procedure is read-only and requires the declarative [dashboard](../monitoring/dashboards/README.md) to have been created by a separately reviewed plan and authorized apply. Missing access or missing dashboard is a reason to stop; do not create it, modify IAM, or enable collectors from this procedure.

1. Run [runtime release correlation](#runtime-release-correlation) first. Privately identify the current workload, immutable digest, source/build/verification/trust context, release, target, and rollout.
2. Open **Sample service deployment health** in Cloud Monitoring for the reviewed project. Select exactly one environment: dev, stage, or prod. Do not use wildcard/all-environment selection for release review.
3. Select an observation window after the reviewed rollout, allow ingestion delay, and inspect sample freshness. A window spanning releases cannot attribute all behavior to the latest release. Wider windows can increase alignment intervals.
4. Compare available and desired replicas. Require fresh positive desired counts and matching available counts; inspect raw collector series if they disagree. Conservative interval extrema can show a temporary gap during transitions. Confirm Deployment observed generation and owned Pod readiness using [runtime validation](#runtime-validation). Scale-to-zero and missing/stale samples are not success.
5. Inspect application responses excluding health checks, 4xx/5xx counts including both classifications, and separate health-check responses. Counts are per aligned interval, not rates. Sparse application traffic and empty error series are possible; absence is not proof of zero errors. Do not generate traffic or artificial failures to fill charts.
6. Inspect server handling p95 for non-health requests. Distributions are merged across Pods before estimating the percentile. This is histogram-based server duration, not client latency or an SLO; low sample counts and extraction gaps limit interpretation. Use [metric inspection](#release-health-metric-inspection) to compare distribution/request counts and investigate missing evidence.
7. Recheck runtime release identity after review. Privately record the environment/window and evidence gaps, then explicitly continue, hold, or reject release evaluation. Dashboard health does not establish provenance, verification, attestation validity, Binary Authorization admission, Cloud Deploy identity, or promotion authorization. No approval, promotion, rollback, or other mutation follows automatically.

## Release-health alert review

This workflow is read-only. The [availability policy](../monitoring/alert-policies/README.md) is deployed through a reviewed exact saved-plan apply that added only the policy. Healthy-state live validation confirmed fresh available=1/desired=1 values across dev/stage/prod, a non-firing condition, zero firing/acknowledged alerts, no active alerts for this policy, and an unchanged dashboard. A real FIRING lifecycle and duplicate collectors were not exercised live; no artificial failure was induced. Use existing Monitoring read access; missing policy/access is a reason to stop, not permission to create resources, change IAM, or enable collectors.

1. In Cloud Monitoring Alerting, inspect **Sample service deployment availability review**, its enabled state, condition, and Alerts section. Compare the live query, 30-second evaluation interval, 120-second duration, and empty notification routing with the canonical definition. No incident alone is not success.
2. Identify namespace/environment from the query result or incident labels, plus project/location/cluster/deployment. Require dev, stage, or prod and deployment sample-service; never join unrelated environments. Keep raw identifiers private.
3. Run [runtime release correlation](#runtime-release-correlation) for that environment. Confirm current owned workload, immutable digest, release/target/rollout, and source/build/verification/trust context. An old incident can concern a different release.
4. Inspect fresh raw available/desired gauges using [metric inspection](#release-health-metric-inspection) and compare with Kubernetes desired replicas, observed generation, availability, and Pod readiness. MIN available/MAX desired avoids duplicate collector summation; inspect collector disagreement and sample timestamps. Desired zero or missing/stale metrics is missing health evidence. Do not scale, delete Pods, alter readiness, or generate failures to test firing.
5. For reproducible query inspection, resolve the checked-in PromQL locals with the reviewed private project/location/cluster inputs and query the existing API. POSIX shell example; QUERY is the exact resolved condition, not a new threshold:

```sh
PROJECT_ID='<PROJECT_ID>'
QUERY='<EXACT_RESOLVED_PROMQL_CONDITION>'
ACCESS_TOKEN="$(gcloud auth print-access-token)"
curl --fail --silent --show-error --get \
  "https://monitoring.googleapis.com/v1/projects/$PROJECT_ID/location/global/prometheus/api/v1/query" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  --data-urlencode "query=$QUERY"
unset ACCESS_TOKEN
```

Require a successful API response without warnings and inspect component vectors separately. An empty condition result means no mismatch was detected; it is not proof of healthy state when component vectors are absent/stale. Retain environment labels when inspecting all three namespaces. See [Prometheus query API](https://docs.cloud.google.com/stackdriver/docs/managed-prometheus/query-api-ui).

6. Perform [deployment health dashboard review](#deployment-health-dashboard-review) for the same environment/window. Errors remain combined 4xx/5xx evidence; sparse non-health latency does not justify a threshold. Privately record evidence gaps and explicitly decide continue, hold, or reject release evaluation.

Alert review does not itself authorize promotion, approval, rejection by infrastructure, rollback, redeployment, trust changes, or any cloud mutation. All such actions require separate explicit authorization. This procedure changes no policy or notification routing.

## Manual release rejection and rollback

The sequence is release review → reject → stop further progression → identify rollback need → review rollback candidate → separate authorization → rollback execution → post-rollback validation. Rejection is a review record; rollback is a distinct cloud mutation. Neither an alert nor a reject outcome executes recovery.

### Record rejection and stop progression

Complete the [release review checkpoint](#release-review-checkpoint), retaining the failed release and evidence. Record the environment, release/target/rollout, exact immutable digest, source revision, producing build ID/identity, UTC timestamp, rejection reason/evidence, and exactly one rollback need: required, deferred, or not applicable. Explain the selected need: a rejected candidate that never changed the environment may need no rollback; a deployed failure may require restoration; uncertainty may defer recovery while investigation continues.

Stop issuing further promotions and approvals for the rejected candidate. This is an explicit procedural stop, not an automatic infrastructure lock: the record does not cancel queued/in-progress jobs, revoke permissions, suspend the pipeline, or abandon a release. Inspect concurrent/pending rollouts read-only. Do not grant a pending approval and compensate afterward. Any server-side approval rejection, cancellation, or suspension is a separate mutation needing its own explicit authorization; resolve an active competing deployment before rollback authorization. Do not retry/redeploy, rebuild, resign, modify trust, or erase rejection evidence automatically.

Copy this record into ignored private validation storage; keep public extracts placeholder-only:

```text
rejected_at_utc: <UTC_TIME>
environment: <ENVIRONMENT>
rejected_release / target / rollout: <RELEASE> / <TARGET> / <ROLLOUT>
immutable_digest: sha256:<DIGEST>
source_repository / source_revision: <SOURCE_REPOSITORY> / <FULL_COMMIT_SHA>
producing_build / build_identity: <BUILD_ID> / <BUILD_SERVICE_ACCOUNT>
decision: reject
reason_and_evidence: <REASON_AND_TIMESTAMPED_EVIDENCE_REFERENCES>
progression_stop: <NO_FURTHER_PROMOTION_OR_APPROVAL_AND_CONCURRENT_STATE>
rollback_need: <ONE_OF_required_deferred_not_applicable>
rollback_need_reason: <REASON>
```

### Validate a previously accepted rollback candidate

Select an explicit previously accepted release and successful prior rollout for the affected target, with its acceptance evidence; do not infer acceptance merely from render success or choose the latest release automatically. An already running candidate in the same environment is not a restoration to an earlier release. Successful historical rollout is deployment evidence, not sufficient trust or health acceptance by itself.

1. Join the historical release annotations, successful target rollout/deploy job, acceptance record, source revision, producing build ID/identity, and immutable approved image reference. Read the image by digest in Artifact Registry and the successful producing build. Require retained passed trusted verification output for this exact candidate, not a claimed annotation alone. A mutable-tag-only candidate is blocked; never rebuild historical source, retag, substitute a digest, or create replacement artifacts to make it eligible.
2. Use [attestation inspection](#attestation-inspection) with reviewed settings and `--inspect-only`: exact subject/digest, occurrence, expected attestor/note/key, and VERIFIED signature. Require compatibility with current [Binary Authorization enforcement](trusted-delivery.md#runtime-admission), without trust mutation, bypass IAM, policy overrides, or break-glass. Missing or invalid trust blocks rollback; prior admission is not a waiver of current enforcement.
3. Compare the historical pipeline/target snapshot with current configuration: affected namespace/profile/APP_ENV, cluster, deploy authority, standard strategy, approval requirements, and rendered application resources. Require the same candidate digest and canonical source/build/verification/trust annotations. Inspect full manifests for configuration changes, unexpected containers, hooks, build/image overrides, or data/schema incompatibility. The selected release restores its rendered configuration as well as its image; image equality alone is insufficient. This workflow does not reverse data changes.
4. Inspect the actual release source URI, targetArtifacts and phaseArtifacts. Read each required source archive, rendered manifest, and effective Skaffold object at its recorded generation; compare source SHA-256 with the reviewed release annotation and rendered bytes with retained reviewed evidence. Record object generations/hashes, bucket ownership/location/protection, retention expiration, lifecycle/deletion exposure, and readability by the existing deploy execution authority. Do not assume object existence proves execution-identity access. Follow [artifact protection](trusted-delivery.md#source-and-rendered-artifact-protection): require at least the established 75-minute deployment + validation protection margin, longer if the reviewed execution window requires it. An object still readable after retention expiry fails this gate; soft-deleted bytes are not live executable material. Missing/unavailable material, expired protection, unverified hashes/access, or insufficient margin blocks execution. Do not silently recover, upload, recreate a release, relax retention, or change IAM.
5. Record compatibility and any missing/conflicting evidence. Re-read current affected workload and snapshot all other environments' Deployment UID/generation/spec, owned Pod UIDs/digests, release/rollout identity, and admission state for post-action comparison. Require no unaccounted active/queued rollout, an unused rollback rollout ID, and a reviewed execution plan. Candidate identity may be valid while rollback remains blocked by storage protection; report both separately.

### Cloud Deploy execution boundary

The selected mechanism is [Cloud Deploy target rollback](https://docs.cloud.google.com/deploy/docs/roll-back): one new rollout of an explicitly selected existing accepted release in one target. It preserves that release's immutable image and rendered material; no new release/source upload/application build is part of this workflow. Always supply `--release` and an unused `--rollout-id`; never use automatic last-successful selection. See the [command reference](https://docs.cloud.google.com/sdk/gcloud/reference/deploy/targets/rollback).

Only after all candidate checks pass and separate explicit authorization identifies the exact project/pipeline, environment, prior release/digest, new rollout ID, expected mutations, and approval boundary, the following mutation may be executed:

```sh
gcloud deploy targets rollback <TARGET> \
  --project=<PROJECT_ID> --region=<REGION> \
  --delivery-pipeline=sample-service \
  --release=<PREVIOUS_ACCEPTED_RELEASE> \
  --rollout-id=<NEW_ROLLBACK_ROLLOUT_ID>
```

This creates a rollout and triggers normal Cloud Deploy execution/jobs and artifact/log writes; dev can deploy immediately. Review existing execution permissions before authorization; this procedure grants none. Stage/prod retain `requireApproval=true`: inspect the new rollout and require PENDING_APPROVAL/NEEDS_APPROVAL before any deployment, then use the existing [separately authorized approval procedure](#controlled-promotion) for this rollback rollout under the selected prior release. Do not assume historical approval authorizes the new rollout. Unexpected approval/execution behavior stops the procedure and requires review, never an override or compensating mutation. No rollout, promotion, approval, rollback, upload, or cleanup is authorized by this documentation itself.

Keep both the rejected rollout and the new rollback rollout in the record; do not rewrite history. On failure, stop and preserve diagnostics. Do not retry, choose another candidate, recreate a release, or use direct kubectl mutation, the direct deployment consumer, or manual Skaffold apply as an alternate rollback path. Multiple rollouts under the prior release can make normal runtime attribution ambiguous: inspect this exact authorized rollout/job and timeline against the pre/post UID/generation observations; release labels alone cannot select an attempt.

```text
rollback_reviewed_at_utc: <UTC_TIME>
rejection_record: <REFERENCE>
affected_environment / target: <ENVIRONMENT> / <TARGET>
previous_accepted_release / prior_rollout: <RELEASE> / <PRIOR_ROLLOUT>
acceptance_evidence: <TIMESTAMPED_REFERENCE>
candidate_digest / source_revision / producing_build: sha256:<DIGEST> / <FULL_COMMIT_SHA> / <BUILD_ID>
build_identity / verification / trust: <BUILD_SERVICE_ACCOUNT> / <VERIFICATION_EVIDENCE> / <ATTESTATION_EVIDENCE>
target_and_admission_compatibility: <RESULT_AND_EVIDENCE>
source_render_generations_hashes_and_protection: <READBACK_RESULTS_AND_REMAINING_MARGIN>
execution_authority_access: <READ_ACCESS_EVIDENCE_OR_BLOCKED>
other_environment_baseline: <PRIVATE_SNAPSHOT_REFERENCE>
rollback_executable: <YES_OR_NO_WITH_BLOCKERS>
proposed_command_and_new_rollout: <EXACT_COMMAND_AND_UNUSED_ID>
separate_authorization: <AUTHORIZATION_REFERENCE_OR_NOT_AUTHORIZED>
post_rollback_result: <NOT_EXECUTED_OR_TIMESTAMPED_VALIDATION_REFERENCE>
```

### Post-rollback validation

After an authorized execution, require the exact new rollout's successful deploy job, terminal SUCCEEDED state, and expected approval state; command exit success alone is insufficient. Run [runtime release correlation](#runtime-release-correlation), resolving multiple historical attempts explicitly as above. Confirm the selected candidate digest in template/owned Pods/actual imageID, matching source/build/verification/trust and prior release identity, target environment, observed generation, positive desired replicas, equal updated/available replicas, and Ready owned Pods. Recheck valid attestation and enforced Binary Authorization with no bypass. Perform [alert review](#release-health-alert-review) and [deployment health dashboard review](#deployment-health-dashboard-review), recording freshness, evidence gaps, and any active alert rather than treating no alert as proof of health. Compare every unrelated environment with its pre-action snapshot; require unchanged workload spec/UID/generation, owned Pod identity/digest, and release/rollout state, or investigate before claiming isolation. Record the new [release review outcome](#release-review-checkpoint) and reason; rollback success does not authorize further promotion. Failure or ambiguity stops evaluation and permits no automatic corrective mutation.

### Offline rejection and rollback scenarios

| Scenario | Expected result | Boundary |
| --- | --- | --- |
| Reject before deployment; rollback not applicable | progression stopped | No rollback, retry, redeploy, or trust mutation |
| Reject deployed release; accepted immutable candidate and all gates pass | authorization required | No execution until separate explicit authorization; stage/prod approval remains separate |
| Candidate image or required source/render material unavailable | rollback blocked | No rebuild, substitution, or silent recovery |
| Source/render bytes readable but retention expired or margin insufficient | rollback blocked | Readability does not satisfy protection |
| Candidate trust missing or invalid | rollback blocked | Health or historical admission cannot override trust |
| Candidate identified only by mutable tag | rollback blocked | Require previously accepted immutable digest |
| Concurrent rollout or target/authority mismatch | rollback blocked | Resolve ambiguity through separate review, never bypass |

### Read-only feasibility finding

Release history inspection found a previous candidate successfully deployed to dev/stage/prod, while a later accepted release is current in dev. A separate rendered-only release has no rollout and is not a previously accepted rollback candidate. The prior candidate image remained available, source/build/digest identity agreed, retained trusted verification passed, attestation signature validation returned VERIFIED, and current dev target/admission configuration was compatible.

The prior release source archive and dev rendered manifest/effective Skaffold objects were readable; source read-back matched the recorded archive SHA-256 and rendered manifests retained the expected digest/namespace. Their retention protection had expired, however, leaving less than the required execution/validation margin. Thus a prior trusted identity exists, but no fully eligible executable dev rollback candidate was established. Rollback is blocked under the existing protection contract; no recovery, re-upload, re-render, new release, or configuration change was attempted. This is an observation, not a durable inventory or authorization; every future attempt requires fresh checks. No rollout or workload mutation occurred.

## Release review checkpoint

This is the canonical read-only checkpoint for dev, stage, or prod. It combines release identity, trust evidence, deployment state, and operational evidence into exactly one recorded decision: `continue`, `hold`, or `reject`, with a reason. It creates no service, evidence database, or enforcement gate. Review assertions and runtime annotations are correlation evidence, not cryptographic proof.

### Collect and reconcile evidence

1. Identify the intended environment, release, target, rollout, immutable image digest, source repository/revision, producing build ID and build identity from reviewed candidate/configuration. Record UTC review time and observation window after the rollout. Use existing read access; a failed read is missing evidence, not permission to change IAM or recover resources.
2. Perform [runtime release correlation](#runtime-release-correlation) completely. Join the intended candidate to Cloud Deploy release annotations, target snapshot/current target, one unambiguous successful rollout and deploy job, Deployment and UID-owned Pods, desired image and actual imageID. Require consistent source/build/digest, environment, and deployment authority. Inspect the producing build read-only (`gcloud builds describe <BUILD_ID> --project=<PROJECT_ID> --region=<REGION>`): require successful execution, reviewed source revision and build identity, and matching produced digest. Inspect retained trusted verification execution/result for this same candidate; syntax validation or a workload's passed annotation alone is insufficient. Missing history is incomplete evidence; a confirmed wrong digest/source is conflicting evidence.
3. Perform [attestation inspection](#attestation-inspection) using reviewed settings and `--inspect-only`. Require the exact immutable subject, expected attestor/note/key, and VERIFIED signature validation; compare the inspected occurrence with the candidate trust reference. Read the current Binary Authorization policy and cluster enforcement (`gcloud container binauthz policy export --project=<PROJECT_ID>` and `gcloud container clusters describe <GKE_CLUSTER> --project=<PROJECT_ID> --location=<ZONE>`). Require the [protected cluster rule](trusted-delivery.md#runtime-admission), configured attestor, REQUIRE_ATTESTATION, ENFORCED_BLOCK_AND_AUDIT_LOG, and PROJECT_SINGLETON_POLICY_ENFORCE. Inspect workload annotations for break-glass and other overrides, and existing deployment/admission events or audit evidence where retained. A Ready Pod alone does not establish past admission policy; record the historical evidence and its retention limitations. Do not bypass admission, sign, or mutate trust to complete a review.
4. Inspect [deployment state](#runtime-validation): non-zero desired replicas, observed generation, updated/available replicas matching desired, Running/Ready owned Pods, successful correlated rollout/deploy job, expected approval state, and no unexplained containers or replacement. Failed rollout attribution or confirmed release-specific readiness failure can support reject; unsettled or ambiguous state requires investigation. Re-read runtime identity at the end; changed UID/generation/Pod/digest invalidates the mixed observation and requires hold and a fresh review.
5. Perform [alert review](#release-health-alert-review), including the policy's Alerts section and fresh component vectors, then [dashboard review](#deployment-health-dashboard-review) for exactly the same environment/window. Record enabled policy, condition, active alert state, sample timestamps, desired/available values, and dashboard query scope. A firing alert requires investigation, not automatic rejection or rollback. No alert or an empty condition vector alone does not prove health.
6. Inspect [structured logs](#application-log-inspection) and [request/error/latency metrics](#release-health-metric-inspection) for the correlated workload as needed. Record missing, stale, conflicting, and sufficient evidence separately. Missing operational evidence normally means hold. If non-health traffic/latency or error series are absent, explicitly record that gap: continue is defensible only for a bounded availability review with fresh deployment gauges, readiness, existing probe logs/health series, and no unresolved condition; it makes no application-traffic, latency-target, or zero-error claim. If the release stage requires those absent signals, hold. Do not generate traffic or induce failures.
7. Apply the decision rules below, record one outcome and a concrete reason, evidence references, limitations, and follow-up. Keep detailed identifiers/raw output in ignored private validation storage; use only placeholders and sanitized conclusions in public material. Any later promotion requires separate authorization and fresh execution preflight, including source/render artifact availability and retention. A continue review is not an executability guarantee after artifacts expire.

### Decision rules and offline scenarios

Confirmed invalid identity/trust or a defensible release-specific failure takes precedence over healthy signals. Ambiguity or unavailable evidence is not a confirmed failure. Review all four evidence groups before continue; there is no score or majority vote.

| Scenario | Decision | Reason / boundary |
| --- | --- | --- |
| Consistent identity, valid trust, settled deployment, sufficient fresh operational evidence | continue | No unresolved condition for the stated review scope; separate promotion authorization still required |
| Healthy workload, invalid signature or unexpected immutable digest | reject | Health cannot override failed trust or identity |
| Healthy workload, missing trust evidence | hold | Trust is not established; confirmed invalid evidence instead requires reject |
| Valid trust, stale or missing required operational evidence | hold | Absence is not health evidence |
| Valid trust, firing alert with unexplained cause | hold | Investigate; no automatic rejection or rollback |
| Valid trust, confirmed release-specific deployment or operational failure | reject | Record the failure evidence; rollback requires separate authorization |
| Ambiguous rollout attribution or changing runtime identity | hold | Collect a coherent observation before deciding |
| Sparse non-health traffic, fresh readiness/gauges/probe evidence, bounded availability scope | continue | Explicitly accept the traffic/latency evidence gap for this scope only |
| Sparse non-health traffic when application performance evidence is required | hold | Alternative availability evidence does not satisfy the required scope |

Healthy but untrusted must not continue. Trusted but unhealthy must not continue automatically. Missing trust evidence means hold or reject, never continue. `continue` neither authorizes nor executes promotion. `reject` records the decision and does not execute rollback. This checkpoint performs no promotion, approval, rollback, redeployment, build, signing, trust mutation, or other cloud mutation; it introduces no bypass path.

### Review record

Copy this template into ignored private validation storage, replace every placeholder, and choose exactly one decision (never a list). Evidence references must identify actual reads and timestamps; filling the template is not evidence verification. Inaccessible evidence must be recorded as missing rather than passed. Public extracts must retain placeholders for sensitive identifiers.

```text
reviewed_at_utc: <UTC_TIME>
observation_window_utc: <START_UTC> / <END_UTC>
environment: <dev_or_stage_or_prod>
review_scope: <REQUIRED_EVIDENCE_AND_STAGE>
release / target / rollout: <RELEASE> / <TARGET> / <ROLLOUT>
artifact_identity: <APPROVED_IMAGE>@sha256:<DIGEST>
source_repository / commit_sha: <SOURCE_REPOSITORY> / <FULL_COMMIT_SHA>
build_id / build_identity: <BUILD_ID> / <BUILD_SERVICE_ACCOUNT>
runtime_identity: <DEPLOYMENT_UID_GENERATION_AND_OWNED_POD_UIDS>
identity_evidence: <REFERENCES_AND_MATCH_RESULTS>
trust_evidence: <VERIFICATION_ATTESTATION_SIGNATURE_AND_ADMISSION_RESULTS>
deployment_evidence: <ROLLOUT_APPROVAL_READINESS_AND_FINAL_IDENTITY_RECHECK>
operational_evidence: <ALERTS_DASHBOARD_FRESH_GAUGES_LOGS_AND_METRICS>
missing_or_conflicting_evidence: <GAPS_OR_NONE_AND_SCOPE_JUSTIFICATION>
decision: <ONE_OF_continue_hold_reject>
reason: <CONCRETE_REASON_LINKED_TO_EVIDENCE>
limitations_and_follow_up: <REMAINING_GAPS_AND_SEPARATE_AUTHORIZATION_BOUNDARY>
```

### Healthy-state validation

A read-only dev review recorded `continue` for bounded deployment availability: runtime/release/rollout/source/build/digest correlation agreed, retained trusted verification passed for that candidate, exact-subject attestation signature validation returned VERIFIED, current admission enforcement was active without a workload override, and the correlated deploy job/rollout succeeded. Fresh desired/available replicas were 1/1 with an unchanged owned Ready workload. Scoped dashboard queries were accepted, probe logs returned HTTP 200, the availability condition was non-firing, and review-time Cloud Monitoring UI evidence showed zero firing/acknowledged alerts and an empty active Alerts list.

Non-health response/error/latency series were absent; fresh readiness, deployment gauges, and probe evidence supported this bounded scope only. Historical admission enforcement was not independently reconstructed from retained events. This review does not establish application performance, zero errors, future artifact availability, or promotion authorization. Hold/reject scenarios above were checked offline; no failure, traffic, or cloud mutation was induced. Detailed identity and evidence references remain private.

## Validation scenarios

| Scenario | Expected result |
| --- | --- |
| Trusted happy path | Same digest/correlation, successful rollout, internal health |
| Pre-release failure | Rejection before signing/release/promotion |
| Untrusted admission | Fresh unattested Pod request rejected; separately authorize live test |
| Stage/prod control | Pending approval, separate approval before deployment |
| Runtime review | Runtime correlation and read-only deployment health dashboard review; deployed availability policy and healthy-state alert validation; real FIRING lifecycle and duplicate collectors were not exercised live |

Offline negatives make no cloud calls. Live tests, cleanup, retry, and rollback need explicit authorization. Simulations are not live IAM denial/admission evidence.

## Infrastructure and credential safety

Review fresh locked plans before separately authorized apply:

```sh
terraform -chdir=terraform/foundation fmt -check
terraform -chdir=terraform/foundation validate
terraform -chdir=terraform/foundation plan -input=false -lock=true -lock-timeout=60s -out=/local/foundation.tfplan
```

Use existing backend/private inputs; stop on unrelated drift, replacements, or destroys. Never manually enable APIs, migrate state, or change IAM during troubleshooting. An authorized saved-plan apply uses that exact reviewed plan, without unauthorized regeneration.

Tokens, temporary kubeconfig/CA, private tfvars, state, and binary/JSON plans remain private. Direct execution isolates/removes temporary material; never publish credentials or raw sensitive provider output.
