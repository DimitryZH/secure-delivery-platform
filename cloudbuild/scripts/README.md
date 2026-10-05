# Cloud Build Scripts

Place helper scripts here when the CI flow becomes complex enough to justify extraction.

Examples:
- metadata preparation
- release manifest rendering
- verification helpers

`verify-release-metadata.py` implements the offline release metadata gate used
by `cloudbuild-verify.yaml`. It emits JSON to stdout and exits nonzero on
rejection. See [verification usage and limits](../../docs/trusted-delivery.md#verification).

`attest-release.py` reruns verification under the separate attestation identity,
signs the digest-pinned subject with KMS, requires signature validation, and
creates/inspects the occurrence. `--inspect-only` performs no signing or writes.
See [authority boundary and runbook](../../docs/trusted-delivery.md#attestation).
