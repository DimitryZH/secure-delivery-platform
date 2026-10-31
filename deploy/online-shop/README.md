# Catalog deployment in dev

Implements the first stage of [#93](https://github.com/DimitryZH/secure-delivery-platform/issues/93).
Implementation and offline checks are distinct from read-only observations and
live acceptance. See [validation.json](validation.json). The separately authorized
infrastructure apply completed from `1b474a96ac344b3ee978b7d4df373d86d62cebee`.
[Collector adoption](collector-adoption.md) adds the narrow mirror/separate-signing
implementation and live publisher proof. The authorized mirror upload completed;
a Collector-specific blob transport fix now has read-only verification of its
existing layers and awaits review/merge. **Signing and workload rollout remain
pending.** Eligibility is not authorization.

## Release and deployment boundaries

The application remains the accepted `catalog-v1` release from [#87](../../cloudbuild/online-shop/README.md).
Its producing configuration is `6043c9af617274fcdc97dc9828b4356c72061dd1`, AML
is `89fd1cde8285761cc2a35dfb22d145adb2eed980`, and build is
`b4c1e382-e23a-465c-b6b4-e7093af95391`. Exact accepted release identity, digest,
signing build, candidate generation and transport hash are fixed in [policy.json](policy.json).
They are never replaced by the deployment revision. The application is not rebuilt,
retagged or reattested to add deployment code.

`workflow.py prepare` independently fetches the pinned AML plan and queries actual
build/registry evidence through the existing verifier. It recomputes candidate
identity/membership, revalidates the digest-bound occurrence/signature, checks
the accepted signing execution and retrieves the exact retained candidate generation.
Sanitized examples and prior success booleans are not execution inputs.
The selected deployment revision must be on canonical main and every executing
trust/configuration file must match it. There is no feature-source override.

Preparation writes a new local bundle only after all application and supporting
proofs pass. It cannot run a rollout. Rendering fixes one application container
and one independently governed supporting container; exact-object comparison
rejects additional objects, sidecars, init/ephemeral containers, tags, substituted
images, admission bypasses or changed Collector configuration. It records the
producing and deployment revisions separately, along with both image sets,
configuration identity and rendered bytes hash.

Local prepared manifests and Cloud Deploy rendered artifacts have separate inventory
modes. Prepared manifests remain canonical object matches to local rendering.
Rendered preflight additionally requires the six documented
[automatic Cloud Deploy labels](https://docs.cloud.google.com/deploy/docs/labels-annotations#automatic_labels_from_cloud_deploy)
at resource metadata and Deployment/DaemonSet Pod-template metadata: fixed
`app.kubernetes.io/managed-by=google-cloud-deploy` and exact project, location,
pipeline, release and target IDs. Expected values come from separately reviewed
Cloud Deploy API release/target context and the explicitly intended full release
resource, never from the labels being checked. Only those additions are modeled;
unknown labels/metadata, selectors, images, annotations, configuration and security
changes still fail exact comparison. Label generation remains enabled.

`acceptance.py runtime` and `signals` first apply the shared candidate policy guard:
exact schema reconstruction and integer version 1, recomputed release-set identity,
and binding to the accepted catalog-v1 membership/source/build/digest. No Pod or
telemetry evidence is processed before that guard. Matching supplied readbacks
cannot redefine the expected release, and recomputing an unaccepted release's
identity does not authorize it. This local guard supplements the fresh independent
cloud verification required by preparation/preflight; it does not replace it.

The `catalog-dev` pipeline reuses the existing dev target/execution identity and
artifact bucket. It has only a dev stage. Existing sample-service preparation,
pipeline, stage/prod progression, manifests and decision controls remain intact.
There are no Skaffold builds, hooks, `--images` substitutions or public Services.

## Runtime and telemetry

Catalog runs the accepted scratch image's `/src/server` against local
`/src/products.json`; no cloud database, profiler, Redis or other shop service is enabled.
It uses port 3550, non-root UID/GID 1000, read-only root, dropped capabilities,
RuntimeDefault seccomp, no service-account token, linux/amd64 scheduling, bounded
100m/64Mi requests and 200m/128Mi limits. Native gRPC startup/readiness/liveness
probes do not assume reflection. A 30-second shutdown grace exceeds AML's validated
20-second aggregate shutdown budget. One surge catalog Pod is budgeted.

SDK OTLP/gRPC traces and metrics go only to the internal Collector Service.
Cloud Trace is the trace backend; **Cloud Monitoring is the sole application metric
backend** (`workload.googleapis.com` prefix). Metric resource filters explicitly
retain version, environment, release-set ID and component digest; functional
operation/kind/outcome dimensions remain bounded. Sampling is 0.1 for new roots;
acceptance sends an explicit sampled W3C parent for a known trace ID.

Collector Contrib 0.164.0 is selected because this distribution includes Google Cloud
export and file-log parsing. Its exact linux/amd64 manifest/config/index digests,
upstream repository and exact Sigstore workflow identity are pinned in policy.
The [official release](https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.164.0)
and [exporter configuration](https://github.com/open-telemetry/opentelemetry-collector-contrib/blob/v0.164.0/exporter/googlecloudexporter/README.md)
are the source references. Live Cosign verification of the exact index and
publisher, unique linux/amd64 membership and actual manifest/config/layer hashes
passed on 2026-10-30. The uploaded mirror passed read-only content verification
with the proposed Collector-specific redirect fix; platform attestation remains pending.

`verify_support` requires successful online Cosign verification of that signed
index, its exact amd64 member, the same digest-addressed bytes/config/platform in
the approved Artifact Registry mirror, and a valid platform-attestor occurrence
for that exact mirrored URI. It never mirrors or signs. There is no arbitrary-image
signing entry point, registry exception, namespace exception or break-glass path.
The separate [adoption CLI](collector-adoption.md) repeats these proofs inside the
existing attestation identity before signing only this policy-selected support image.
The Collector is not an AML-built member of `catalog-v1`.

The Collector DaemonSet runs one agent per eligible node. Only catalog log paths
`/var/log/pods/dev_productcatalogservice-*/catalog/*.log` are read. Root UID is
required for node-owned log files; the Pod is nonprivileged, drops all capabilities,
has no host PID/network or Kubernetes API RBAC/token, mounts pod logs read-only,
and writes only bounded cursor storage in an emptyDir. The host mount still grants
visibility into the node log directory: reviewed immutable configuration and image
are part of this trust boundary. Linux file permissions and cursor/rotation behavior
remain live acceptance checks; Windows parser validation does not establish them.
Memory, queues and export deadlines are bounded; there is no durable telemetry spool
or lossless-export claim. Collector rollout may briefly interrupt export.

Stdout has one ingestion owner: Collector parses CRI and application JSON, maps
timestamps/severity, converts integer sampled flags to two-digit hex and maps
trace/span fields into native OTLP log context. The Google exporter writes
`online-shop/catalog` with native Cloud Logging trace linkage. The scoped project
exclusion drops only the original GKE-agent **catalog stdout** copy. Sample logs and
Collector-exported logs remain eligible for ingestion. Existing project sinks were
only `_Default`/`_Required`; fresh preflight must review any additional sinks and
prevent duplicates. No application SDK log exporter is added.

`trace_id` in JSON alone is not native LogEntry linkage. `acceptance.py signals`
requires the real native trace/span fields to match a nonempty Cloud Trace span,
the test traffic window, service/version/dev labels, release-set ID and digest,
plus nonzero functional application metrics. Empty views and config presence fail.

## Infrastructure and capacity

The following proposal was separately applied from the merged configuration above:
8 creates, 2 updates and import of the existing default pool, without Terraform
delete/replace. GKE internally recreated the node through surge; sample-service
experienced approximately 43–49 seconds of sampled HTTP 503 and recovered in all
three environments. Fresh post-apply readback confirmed workload pool, metadata
server, scoped Collector grants/exclusion and dev-only pipeline. Historical plan
and pre-apply observations below remain distinct from that completed apply.
The post-apply snapshot had 1069m CPU / 4796Mi memory free by requests and 90 Pod
slots, with no Pending Pods. Recheck this again before any workload rollout.

[catalog-runtime.tf](../../terraform/foundation/catalog-runtime.tf) proposes a
dedicated Collector GSA and only Trace Agent, Monitoring Metric Writer and Logging
Log Writer roles. Its Workload Identity binding permits only `dev/catalog-collector`.
Catalog, builder and node identities receive no additional exporter roles or keys.
The Collector selects metadata-server-enabled nodes; it must not fall back to node credentials.

[gke.tf](../../terraform/foundation/gke.tf) enables the workload pool and adopts the
existing `default-pool` using a declarative import, then updates its metadata mode.
Cluster create-time `node_config` is ignored because mutable pool ownership moves
to the imported resource; cluster/pool have `prevent_destroy`. No extra pool,
machine type/count change or autoscaling is proposed. Import is **not executed** by
planning. This existing-cluster adoption requires review before apply; pool metadata
updates can disrupt workloads and require a maintenance/readiness check. Do not
apply a plan containing replacement/deletion or unrelated target changes.

Read-only inspection found one ready untainted linux/amd64 e2-standard-2 node:
1930m allocatable CPU, 753m requested CPU, 6025Mi allocatable memory, 1064Mi
requested memory, 18/110 Pod slots. Free scheduling capacity was 1177m / 4961Mi.
Budget 600m / 768Mi: two catalog Pods (200m/128Mi), one Collector (150m/256Mi),
one temporary negative-admission Pod (150m/256Mi), and an extra sample-service
allowance (100m/128Mi) because its existing manifest has no explicit requests.
This allowance is not a sample limit or performance claim: inspect actual usage,
node pressure, quotas, affinity and constraints again before rollout. Recheck after
the metadata server is enabled; Terraform defaults are not live capacity evidence.

## Subsequent live acceptance — separately authorized

Prerequisites: review/merge, fresh read-only confirmation of the already applied
infrastructure, verified Collector publisher provenance, exact mirror and bounded
platform-attestor adoption for **only** the pinned supporting image. None is executed
by this procedure automatically. If any proof is missing, stop. Do not rebuild/sign
the application or bypass admission. Do not enable a general-purpose signing path.
Install reviewed versions of gcloud, kubectl, Skaffold and grpcurl locally;
the adoption verifier bootstraps checksum-pinned Cosign/crane privately.
Local clients avoid extra in-cluster test images. Keep all raw files under ignored
`.local-validation`; do not use public sanitized records as candidate/snapshot inputs.

1. Fetch main; select and record a full immutable deployment revision containing
   these files. Freeze it for the session. Read the accepted references from policy.
   Retrieve the exact candidate object generation into a new private UTF-8 file,
   check its transport SHA-256 and exit status. The real #87 candidate remains a
   valid source; do not redirect failure JSON over it.
2. Fresh read-only preflight: explicit project `sre-platform-staging-507220`, number
   `465837787797`, region `us-central1`, cluster `secure-delivery-platform`, zone
   `us-central1-a`, dev namespace and registry from `deploy/environments.json`.
   Independently check project mapping, cluster enforcement and exact attestor rule,
   no bypass, key/note/accounts, existing sample image/UID/readiness, WI and current
   grants, scopes/conditions, default-pool metadata labels, actual capacity and
   pending Pods, Collector mirror/trust, pipeline/target snapshots and caller actAs.
   Save `nodes` and `pods` in one private JSON snapshot and run:

   ```powershell
   python -B deploy/online-shop/acceptance.py capacity --snapshot $capacitySnapshot
   ```

3. Prepare a **new** local bundle after every proof passes:

   ```powershell
   python -B deploy/online-shop/workflow.py prepare --candidate $candidatePath --deployment-revision $deployRevision --application-occurrence $catalogOccurrence --collector-occurrence $collectorOccurrence --output-dir $bundle
   ```

   Check exit code, preparation.json, exact rendered inventory and Collector config
   hash. Render locally with Skaffold from the bundle directory, profile dev,
   `--offline=true --digest-source=none`, no image overrides. Compare resulting
   objects against the canonical prepared List; do not accept hidden/default images.
4. Create a uniquely named release in pipeline `catalog-dev` with explicit project/
   region, source staging location in the existing Cloud Deploy bucket, and
   `--disable-initial-rollout`. No implicit initial rollout is allowed. Record
   source URI/generation and actual staged archive SHA-256 from readback. Annotate
   release-set ID, producing revision and deployment revision; separately record
   source/rendered hashes as release annotations after render. Check terminal render
   success, exact pipeline/target/source snapshot and Skaffold source path.
5. Download source and rendered generations privately. Hash the **actual archive
   bytes**, compare to independent recorded release annotations, safely parse the
   target manifest, check exact inventory and actual source/configuration files.
   Require availability/live generation and effective retention/delete protection
   of at least **75 minutes** for both artifacts. Soft-deleted objects and lifecycle
   age alone are insufficient. Do not extend observations from earlier runs.
6. Build a fresh independently reviewed snapshot for `workflow.py preflight`.
   Schema: `version=1`, request `{release_set_id,deployment_revision,target:dev,action}`;
   every `release/admission/target/caller/review` section has `observed_at` UTC Z,
   private `evidence_ref`, both identity bindings and all explicitly named boolean
   checks in `evaluate`. Both `artifacts.source/rendered` require those bindings,
   expected/actual SHA-256, availability/live generation and retention expiry.
   `release_annotations.source_sha256/rendered_sha256` bind independently read
   release metadata. `rendered_documents` is the actual parsed document list.
   Include a fresh `clouddeploy` section with the same observation/reference and
   identity bindings, `release_snapshot_matches_current: true`, and independently
   read `release_resource` / `target_resource` full API names. Project, location,
   pipeline and dev target must match reviewed policy. Bind the full intended
   release resource in `request.clouddeploy_release` and the CLI argument below;
   do not extract it or any expected context from checked manifest labels.
   Evidence age is at most **5 minutes**, future tolerance **30 seconds**. Missing,
   unknown or conflicting facts produce BLOCKED, never an inferred success.

   ```powershell
   python -B deploy/online-shop/workflow.py preflight --candidate $candidatePath --deployment-revision $deployRevision --clouddeploy-release $intendedReleaseResource --snapshot $freshSnapshot --intended-action deploy
   ```

   READY is eligibility only. Dev promotion is blocked. Dev rollback eligibility
   additionally needs a previously accepted, earlier, different release and a
   successful prior dev rollout; no rollback is executed by this tool or acceptance.
7. After separate rollout authorization, create exactly one dev rollout for this
   release in `catalog-dev`. Wait boundedly for Cloud Deploy rollout/job terminal
   status and Kubernetes readiness (catalog startup budget 60s; rollout observation
   budget 10 minutes). On uncertain response, find the existing release/rollout/job;
   never blindly recreate it. Read actual Pods, deployments and Collector DaemonSet,
   including desired/ready counts per eligible node. `acceptance.py runtime` checks
   imageID against registry manifest digest and exact release annotations; unknown
   containerd/local image identity is a blocker, not a substitute for registry proof.
8. Obtain `demo.proto` and `grpc/health/v1/health.proto` using `git show` **bytes**
   from the pinned AML revision into a private proto directory. Check their Git blob
   hashes; do not assume reflection. Port-forward only the catalog internal Service:
   `kubectl --context=$explicitContext -n dev port-forward service/productcatalogservice 3550:3550`.
   Use local grpcurl `-plaintext -import-path $protoDir -proto demo.proto`:
   `ListProducts {}` must return the local catalog; `GetProduct` for an ID returned
   by that response must match; `SearchProducts` with a known catalog token must
   return the expected item; missing ID `{"id":"acceptance-does-not-exist"}` must
   return **NOT_FOUND**. Health uses the explicit health proto and empty service,
   expecting SERVING. Watch is deliberately UNIMPLEMENTED, not a rollout failure.
9. Send at most **30 normal ListProducts RPCs at one/second**, separate from probes.
   Record the traffic start time. Supply one chosen sampled `traceparent` through
   grpcurl `-H 'traceparent: 00-<32hex>-<16hex>-01'`; this is test traffic metadata,
   not a credential or image identity. Do not change application sampling settings
   or create an in-cluster traffic generator.
10. Within a bounded 5-minute ingestion wait, GET that actual trace through Cloud
    Trace v1; query Logging `log_id("online-shop/catalog")` for the same native
    `trace` and normal operation; list Monitoring metric descriptors/time series for
    `workload.googleapis.com` and the normal operation/server labels since traffic
    start. Save actual API responses as `{trace,logs,metrics}`. Record real metric
    descriptor names; do not invent a name if exporter normalization differs.

    ```powershell
    python -B deploy/online-shop/acceptance.py signals --snapshot $signalReadbacks --candidate $candidatePath --since $trafficStartUtc
    ```

    Require nonempty sampled server spans, nonzero functional metrics, native
    LogEntry trace/span linkage, matching JSON IDs and actual version/dev/release/
    digest attribution. Confirm the original GKE stdout copy is excluded and no
    other ingestion sink duplicates it. Observe Collector errors/drops and node
    resource pressure; an empty view, JSON trace_id alone or healthy probe is not proof.
11. Negative admission: independently confirm the **upstream** pinned Collector
    URI is pullable linux/amd64 and has no required platform-attestor occurrence.
    Copy the otherwise-valid rendered Collector Pod template into a uniquely named
    temporary dev Pod, changing only its name and image to that upstream digest.
    Preserve valid config, resources, WI, mounts and placement. No extra test image
    is introduced. Budget the 150m/256Mi Pod and stop immediately if admission
    unexpectedly succeeds (it could otherwise duplicate log collection).
    Capture the API denial/event/audit that explicitly names Binary Authorization
    and the missing required attestation for that digest. ImagePullBackOff, malformed
    spec, webhook errors or generic rollout timeout are **not** acceptable evidence.
12. Delete only the exact temporary negative Pod if created, stop only the owned
    port-forward process and local client. Do not delete application/Collector,
    sample resources, release evidence, namespaces or use blanket cleanup commands.
    Re-read the existing sample Deployment/Pod UID, template/image and health;
    compare to the preflight baseline. Record cleanup and final resource pressure.
    Retain linked sanitized conclusions; keep private responses and inputs private.

Infrastructure apply and read-only Collector publisher/content proof have completed.
Reviewed-main mirror verification, platform attestation and workload acceptance
remain pending. Proof of the
existing release, native parser validation and offline fakes do not establish
deployment, admission, functional RPC or catalog cloud telemetry success.
