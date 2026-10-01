# Minimal artifact attestation path

Issue #45 adds one attestor and one KMS asymmetric signing key. A protected
Cloud Build execution rechecks initial release metadata, signs only the
digest-pinned `artifact_identity`, requires cryptographic signature validation,
then creates and reads back an Artifact Analysis attestation occurrence.
No admission policy or deployment is created.

## Gate and output

`cloudbuild/cloudbuild-attest.yaml` runs `cloudbuild/scripts/attest-release.py`
under `secure-delivery-attestation@PROJECT_ID.iam.gserviceaccount.com`. The
script runs the Issue #43 verifier in the same trusted execution. An uploaded
verification result is never accepted as authorization. Missing or rejected
metadata stops before credential lookup, signing, or occurrence writes.

The script creates the standard Binary Authorization simple-signing payload
containing the image reference and immutable digest, hashes the exact serialized
bytes with SHA-256, and asks KMS to sign. The private key never leaves KMS.
`validateAttestationOccurrence` must return `VERIFIED` before creating the
occurrence. Unknown or rejected responses stop the path. Readback checks the
subject, note, key ID, and payload and validates the signature again.

Successful stdout JSON contains `attestation_status=created`, `artifact_identity`,
the full fresh `verification` record, and `trust_signal_ref` naming the occurrence.
Failures exit 1 and emit `attestation_status=failed` and `error`, without a trust
reference. An API failure after creation can leave an occurrence despite a failed
build; inspect before retrying. Retries can produce duplicate occurrences for
the same digest. A rejected metadata check never signs or creates an occurrence.

## Authority boundary

Terraform grants the separate attestation account:

| Scope | Permission |
| --- | --- |
| One KMS key | Signer/verifier, without key management |
| One attestor | Read and validate signatures, without attestor management |
| One note | Attach and inspect occurrences, without note management |
| Project | Custom occurrence create/get/list role; log writer |
| Dedicated source bucket | Object viewer |

The image-build account receives no signing, attestor, note, or impersonation
grants. The signing account has no Artifact Registry writer, deployment, policy
administration, or Cloud Build build-creation role. No attestation trigger or
submitter actAs/tokenCreator grant is created. Before apply, review effective
IAM, including inherited/group grants: the builder must not be able to impersonate
the signer or invoke a privileged trigger that runs arbitrary code as it.

**Signing code, configuration, and submitters are trusted.** Anyone who can
submit arbitrary code under the signer can bypass a script gate and call KMS.
Operators must assemble the signing bundle from a reviewed immutable commit,
copy only candidate JSON into it, and use trusted registry/attestor/key settings.
Do not upload candidate-controlled scripts or reuse the image-build trigger for
signing. This change does not authorize submitters; that is a separate IAM review.

The metadata gate checks syntax and consistency. It does not prove artifact
existence, producer provenance, source authorization, or tag-to-digest binding.
The attestation certifies this specific gate, not those stronger claims.

## Infrastructure review

`terraform/foundation/attestation.tf` prepares three APIs, a separate account,
KMS key ring/key, note, attestor, scoped IAM, and a dedicated staging bucket.
The bucket blocks public access and expires source after seven days. The key
uses software KMS to avoid HSM cost and has `prevent_destroy`. Key rings and
key names are persistent; rotation/lifecycle requires deliberate review. KMS,
builds, logs, and storage incur normal service charges.

```sh
terraform -chdir=terraform/foundation fmt -check attestation.tf
terraform -chdir=terraform/foundation validate
terraform -chdir=terraform/foundation plan -input=false -out=attestation.tfplan
```

Review the full plan, including unrelated drift, before any separately authorized
apply. No apply is part of this implementation. Key version 1 is registered
explicitly; rotation must update both the attestor key and build configuration.

## Run after reviewed provisioning

Use a trusted source bundle containing reviewed scripts/config and the candidate
`release-metadata.json`. The submitter needs separately reviewed build submission,
source upload, and actAs access to the signing account. Do not grant these to the
image builder. Adjust region/repository to approved platform settings.

```sh
gcloud builds submit <trusted-source-directory> \
  --project=<project-id> --region=us-central1 \
  --config=cloudbuild/cloudbuild-attest.yaml \
  --gcs-source-staging-dir=gs://<project-id>-attestation-source/source \
  --substitutions=_LOCATION=us-central1,_REPOSITORY=secure-delivery
```

Inspect without signing or creating an occurrence:

```sh
python3 cloudbuild/scripts/attest-release.py \
  --metadata release-metadata.json \
  --approved-registry <region>-docker.pkg.dev/<project-id>/secure-delivery \
  --project <project-id> --attestor secure-delivery-verification \
  --note projects/<project-id>/notes/secure-delivery-verification \
  --key-version projects/<project-id>/locations/<region>/keyRings/secure-delivery-attestation/cryptoKeys/verification/cryptoKeyVersions/1 \
  --inspect-only
```

Inspection returns `attestation_status=inspected` after exact subject/key/note
matching and cryptographic validation. A read-only reviewer needs occurrence
viewing and attestor verification access, not KMS signing access. Reviewer
grants are not added by this change.

## Validation and policy handoff

```sh
python -B -m unittest discover -s scripts/tests -p 'test_*py' -v
```

Offline tests run the real metadata verifier and simulate KMS, validation, and
occurrence APIs. They cover successful creation, missing/malformed/forged input,
digest mismatch, foreign registry, denied signing, signature rejection before
write, readback mismatch, and inspection without signing. They do not prove
live IAM denial or real KMS cryptography; live signing requires provisioning.

Implementation validation on September 30, 2026:

- Python suite: 13 test methods passed, including both the verification and
  attestation suites and their negative subcases.
- Terraform formatting and validation passed with the existing provider lock.
- Read-only plan for the configured staging project: **17 to add, 0 to change,
  0 to destroy**. Existing build, registry, cluster, and namespaces are unchanged.
  The only deferred data read is the new signing key's public key version.
- Plan command: `terraform -chdir=terraform/foundation plan -input=false -lock=false -no-color -out=attestation.tfplan`.
  No apply, API enablement, IAM write, signing, or occurrence creation was run.
  Generate/review a fresh locked plan before any authorized apply.

Future Binary Authorization policy should require this attestor for the same
immutable digest. That policy must separately arrange the Binary Authorization
service agent's note-occurrence viewing and demonstrate admission allow/deny
behavior. This implementation does not enable enforcement.

References: [Google's attestation flow](https://docs.cloud.google.com/binary-authorization/docs/making-attestations),
[signature validation API](https://docs.cloud.google.com/binary-authorization/docs/reference/rest/v1/projects.attestors/validateAttestationOccurrence),
[KMS signing API](https://docs.cloud.google.com/kms/docs/reference/rest/v1/projects.locations.keyRings.cryptoKeys.cryptoKeyVersions/asymmetricSign).
