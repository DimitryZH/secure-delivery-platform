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

## Runtime validation

Require rollout/deploy job `SUCCEEDED`, expected target, available Deployment, Running/Ready Pods, exact desired/running digest and imageID, preserved annotations/correlation, unchanged previous environments/IAM/admission, and no unauthorized rollout or break-glass/bypass/policy override.

Service stays ClusterIP. Use read-only internal connectivity, such as Kubernetes API service proxy, for `/healthz` and `/`: require HTTP 200, health `status=ok`, root `service=sample-service`, `status=running`, and expected environment. Never add a helper workload, LoadBalancer, or Ingress for this check.

Inspect job logs/ReplicaSet events read-only to distinguish admission rejection, scheduling, and image-pull failure. Deployment acceptance does not imply admitted Pods. Keep raw evidence private and redact before public sharing.

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
