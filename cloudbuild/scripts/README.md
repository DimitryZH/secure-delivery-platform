# Cloud Build Scripts

Place helper scripts here when the CI flow becomes complex enough to justify extraction.

Examples:
- metadata preparation
- release manifest rendering
- verification helpers

`verify-release-metadata.py` implements the offline release metadata gate used
by `cloudbuild-verify.yaml`. It emits JSON to stdout and exits nonzero on
rejection. See [verification usage and limits](../../docs/cloudbuild-verification.md#executable-gate-issue-43).
