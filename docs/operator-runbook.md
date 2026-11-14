# Operator Runbook

Online Shop is the active workload. Sample-service is retired with no restoration
planned; its former operations are [historical](historical/sample-service/README.md).
Follow the [retirement boundary](sample-service-retirement.md) for its removal.

## Preconditions and authorization

Use the reviewed active binding and private isolated credentials/backend/inputs.
Keep the persisted capacity mode; a paused foundation operation does not authorize
resume. Review, eligibility, execution authorization and target approval are separate.
Keep raw evidence, state and saved plans private. Never bypass trust or admission.

## Attestation inspection

Use Online Shop's independent candidate verification and signature inspection for
every application digest and the separately trusted Collector. Preserve KMS,
note/attestor and Binary Authorization enforcement. See [complete delivery](../deploy/online-shop/complete-README.md).

## Release preparation and creation

Use the existing Online Shop complete workflow, approved immutable candidate and
reviewed deployment revision. Protect source/render generations and hashes; never
rebuild, retag or substitute artifacts during deployment. See [complete delivery](../deploy/online-shop/complete-README.md).

## Release decision preflight

Run the independent Online Shop preflight with fresh target, admission, identity,
capacity and protected-artifact evidence. READY is eligibility only; creating a
release or rollout requires separate authorization. Paused workers cannot satisfy
runtime readiness. Historical success does not establish current eligibility.

## Controlled promotion

The current Shop pipeline is dev-only. Stage/prod promotion is future work requiring
a reviewed workload contract and dedicated target approval; do not reuse the retired
sample pipeline. [Rejection and rollback](#manual-release-rejection-and-rollback)
remain manual, separately authorized actions.

## Runtime release correlation

Compare accepted component digests with actual imageIDs, UID-owned Pods, workload
annotations and the exact release/rollout. Keep producer, deployment and validator
revisions distinct. Use [complete acceptance](../deploy/online-shop/complete-README.md)
and [baseline recovery](platform-baseline-recovery.md). Validate every component.

## Runtime validation

With workers running, inspect fresh controller observed generations, positive desired
replicas, Ready/Available owned Pods, endpoints, Redis and bounded Shop HTTP health.
With workers paused, report these gates unavailable; do not resume for validation.

## Application log inspection

Use the existing Collector path and native trace/log linkage. Verify project,
namespace, source/version/release and observation window for each exercised component.
See [Shop telemetry acceptance](../deploy/online-shop/complete-README.md).

## Release-health metric inspection

Use the [Shop dashboard queries](../monitoring/dashboards/online-shop-dev/README.md).
Check fresh timestamps, scope, probe exclusion and duplicate ingestion. Missing data
is not zero errors or successful recovery. Scale-to-zero is not healthy runtime evidence.

## Deployment health dashboard review

Use the retained Online Shop dashboard and six reviewed queries with fresh bounded
journey evidence, without generating traffic unless separately authorized.

## Release-health alert review

Use [Shop monitoring](../monitoring/online-shop/README.md) and its
[incident runbook](../monitoring/online-shop/incident-runbook.md). Check actual policy,
Alerts section, timestamps and component vectors. No alert is not health evidence.
An alert authorizes no rollback or infrastructure mutation.

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

Before execution authorization, verify read-only that the exact rollback caller has effective `clouddeploy.rollouts.rollback` permission on the intended delivery pipeline, accounting for applicable IAM conditions and deny policies. Record the caller, permission-check time, scope, and evidence privately; do not infer permission from a role name or a prior successful deployment. Cloud Deploy Job Runner (`roles/clouddeploy.jobRunner`) supports execution jobs and is separate from rollback-caller authority; it does not establish permission to initiate target rollback. If the permission is absent or cannot be verified, report rollback as blocked pending separately reviewed IAM authorization/change. Do not grant or modify IAM, add permissions automatically, or switch caller to bypass the check. A positive permission check is a prerequisite, not rollback execution authorization.

Only after all candidate checks pass and separate explicit authorization identifies the exact project/pipeline, environment, prior release/digest, new rollout ID, expected mutations, and approval boundary, the following mutation may be executed:

```sh
gcloud deploy targets rollback <TARGET> \
  --project=<PROJECT_ID> --region=<REGION> \
  --delivery-pipeline=<REVIEWED_PIPELINE> \
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
rollback_caller_permission: <CALLER_SCOPE_TIMESTAMP_AND_clouddeploy.rollouts.rollback_EVIDENCE_OR_BLOCKED>
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
