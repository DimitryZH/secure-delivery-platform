# Trusted Delivery

Online Shop is the active workload: independent production and digest verification,
separate KMS-backed attestation, protected Cloud Deploy source/rendering, and
enforced Binary Authorization. See [complete workload delivery](../deploy/online-shop/complete-README.md),
[release model](architecture/release-model.md) and [IAM model](iam-model.md).

## Verification

`cloudbuild/cloudbuild-verify.yaml` runs `cloudbuild/scripts/verify-release-metadata.py`. Supply producer JSON as `release-metadata.json` with reviewed scripts; `_METADATA_FILE` selects another source-relative file. The producer logs JSON; transport remains an explicit handoff.

Trusted configuration supplies `PROJECT_ID`, `_LOCATION`, and `_REPOSITORY`, never candidate metadata. Checks cover six nonempty initial fields, `owner/repo`, lowercase full Git SHA, UUID-shaped build ID, service-account identity, lowercase SHA-256, and exact approved registry path. A tagged producer input can yield pinned `artifact_identity`; pinned input must agree with `image_digest`.

Missing files, malformed/duplicate JSON, foreign registry, invalid identities, and digest mismatch fail with exit 1. Handled outcomes emit status, UTC timestamp, and errors. Input verification/trust claims are ignored. This gate does not prove provenance, source authorization, artifact existence, or tag binding. Failure stops signing/promotion and retains diagnostics without substituting another artifact.

```sh
python cloudbuild/scripts/verify-release-metadata.py \
  --metadata release-metadata.json \
  --approved-registry us-central1-docker.pkg.dev/<PROJECT_ID>/secure-delivery
python -B -m unittest discover -s scripts/tests -p test_release_metadata_verification.py -v
```

## Attestation

`cloudbuild/cloudbuild-attest.yaml` executes `cloudbuild/scripts/attest-release.py` as `<ATTESTATION_SERVICE_ACCOUNT>`. It reruns verification in trusted execution; uploaded verification output is not authorization. Rejection stops before credentials, signing, or writes.

The standard Binary Authorization simple-signing payload binds the immutable subject. KMS signs its exact SHA-256; private key bytes never leave KMS. `validateAttestationOccurrence` must return `VERIFIED` before creation. Readback matches subject, note, key ID, and payload and validates the signature again.

`--key-version` is the bare `projects/.../cryptoKeyVersions/1` KMS request resource. `--public-key-id` is the canonical `//cloudkms.googleapis.com/v1/projects/.../cryptoKeyVersions/1` occurrence/validation URI. Both must identify the same version. Terraform `attestation_key_version` is the canonical URI, not the KMS API name. Custom aliases are unsupported; rotation must update both inputs and the registered attestor key.

Success emits `attestation_status=created`, artifact identity, fresh verification, and occurrence `trust_signal_ref`. Failure emits failed status/error without a trust reference. A failure after creation can leave an occurrence; inspect before retrying. Retries can produce duplicates for one digest.

Assemble signing code/config from a reviewed immutable commit; copy only candidate JSON. Do not accept candidate-controlled scripts or reuse an image-producing build. Submission/source upload/signer `actAs` need separate reviewed authority. The signer cannot publish images, deploy, or administer admission policy. Persistent key-ring names and protected key lifecycle require deliberate review. Builds, KMS, logs, and storage incur charges.

`--inspect-only` matches subject/note/key and validates signatures without signing/writes. Reviewer occurrence-viewing/attestor-verification access is separate from signing. See [IAM Model](iam-model.md) and [inspection procedure](operator-runbook.md#attestation-inspection).

## Cloud Deploy orchestration and rendering

Keep `catalog-dev`, shared `dev` target, deployment identity and protected storage.
Preparation must verify a reviewed deployment revision and exact immutable images;
no build or tag replacement is permitted. The sample deployment path is unsupported;
its historical shared helper is retained unchanged solely for producing-trust compatibility.
See [operator procedures](operator-runbook.md) and [retirement dependencies](sample-service-retirement.md).

## Source and rendered artifact protection

`gs://<CLOUD_DEPLOY_BUCKET>` uses STANDARD in `us-central1`, uniform bucket-level access, enforced public access prevention, disabled versioning, and `force_destroy=false`. Unlocked 86400-second retention prevents byte overwrite/delete during that period. Administrators can change the policy; it is not an irreversible lock.

Source uses `source/<release-name>/`; current outputs use `rendered/dev`; old `rendered/stage` and `rendered/prod` objects remain historical protected material. Prefixes are not IAM boundaries. Target `artifact_storage` does not configure source staging; creation separately supplies `--gcs-source-staging-dir`.

The caller uploads; deploy execution reads source and writes/reads outputs through Cloud Build. Existing agents support execution. Builder/Job Runner grants include inherited project storage access, which bucket IAM cannot revoke. Retention protects bytes without granting builder deployment authority.

Use deterministic reviewed source, unique object names, SHA-256 recorded outside object metadata, and create-only generation preconditions. gcloud stages a copy under a new timestamp/UUID name. Verify the **actual source URI on the release**, downloaded bytes/hash, generation, retention expiration, and bucket ownership/location. Never assume an unversioned URI pins generation.

Before every execution verify source/render availability, hashes, release identity, and remaining protection. Reserve deployment plus validation margin; the validated gate used at least 75 minutes. Stop on mismatch, insufficient protection, expiry, or retention write failure. Do not relax protection automatically.

Lifecycle deletes live objects after seven days; soft delete retains them another seven days. This MVP lifetime is not a permanent promotion deadline or indefinite executability guarantee. Later promotions/retries/rollbacks need review after expiry. Recovery is a separately authorized mutation.

## Runtime admission

The protected cluster rule requires the configured attestor with `REQUIRE_ATTESTATION` and `ENFORCED_BLOCK_AND_AUDIT_LOG`; GKE uses `PROJECT_SINGLETON_POLICY_ENFORCE`. All three namespaces share enforcement. Retained `ALWAYS_ALLOW` for other clusters is outside this boundary.

Global evaluation enables Google-maintained system-image exceptions by image identity, not namespace. Arbitrary images in `kube-system` are not exempt. Custom platform images/unsigned sidecars require attestation. No custom application allowlist or namespace bypass is used.

Admission checks digest-bound signatures, not metadata verification, promotion history, registry selection, or reference syntax. It affects new requests and does not evict existing Pods. Deployment creation may succeed while Pod admission fails; require rollout success and inspect ReplicaSet events. Break-glass is a boundary limitation, never a validation shortcut. Additional clusters/cross-project attestors need explicit review; policy changes need separate authorization.

## Controlled promotion validation

The original sample dev/stage/prod controlled promotion and screenshots are
**historical** [validation evidence](historical/sample-service/README.md).
Online Shop currently has a dev-only pipeline. Stage/prod delivery is future work.

## Release review and rollback

Use [manual release rejection and rollback](operator-runbook.md#manual-release-rejection-and-rollback)
and fresh independent preflight. READY establishes eligibility only, not authorization.
Keep raw evidence private. Paused workers do not establish workload readiness.

Use the [release review checkpoint](operator-runbook.md#release-review-checkpoint) to reconcile independent trust, deployment state and fresh operational evidence.
