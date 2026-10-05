# Cloud Build Scripts

- `verify-release-metadata.py` implements the metadata gate used by `cloudbuild/cloudbuild-verify.yaml`. It emits a verification JSON record and exits nonzero on rejection. See [Verification](../../docs/trusted-delivery.md#verification).
- `attest-release.py` reruns that gate in separate signing execution, signs through KMS, validates the signature, and creates/inspects an occurrence. `--inspect-only` performs inspection without signing or writes. See [Attestation](../../docs/trusted-delivery.md#attestation).

These helpers consume the [Release Model](../../docs/architecture/release-model.md). Authority and execution procedures belong to [IAM Model](../../docs/iam-model.md) and [Operator Runbook](../../docs/operator-runbook.md), rather than this directory index.
