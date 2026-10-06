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

## Validation scenarios

| Scenario | Expected result |
| --- | --- |
| Trusted happy path | Same digest/correlation, successful rollout, internal health |
| Pre-release failure | Rejection before signing/release/promotion |
| Untrusted admission | Fresh unattested Pod request rejected; separately authorize live test |
| Stage/prod control | Pending approval, separate approval before deployment |
| Runtime review | Manual readiness/digest/HTTP checks; dashboards/alerts remain planned |

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
