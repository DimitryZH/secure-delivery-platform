# Cloud Build Verification Expectations

## Purpose

Cloud Build verification is the first executable gate that decides whether a built artifact can become a trusted release candidate.

The MVP verification stage should stay small and understandable. Its purpose is to prove that verification affects deploy eligibility, not to introduce a large security toolchain.

## Verification role in the trusted path

The verification stage sits between artifact creation and deployment trust enforcement:

```text
Build artifact
  → resolve image digest
  → validate release metadata
  → run MVP checks
  → record verification result
  → prepare trust signal input
```

A successful build does not automatically mean the release is deployable. The verification stage must produce enough evidence for the trust model and environment policies to make a deployment decision.

## MVP Cloud Build verification flow

The verification build should remain a separate, reviewable gate after image publication. It consumes the release metadata produced by the build step and either records a deployable verification result or stops before promotion.

Minimum flow:

1. Read the release metadata for the candidate artifact.
2. Confirm required identity fields are present: `source_repository`, `commit_sha`, `build_id`, `build_service_account`, `image_uri`, and `image_digest`.
3. Confirm the image URI points to the approved Artifact Registry location for the platform.
4. Confirm the deployment input can reference the immutable image digest instead of only a mutable tag.
5. Emit `verification_status=passed` only when all MVP checks pass.
6. Emit `verification_status=failed` and stop before promotion when any required check fails.

The verification build should not create a Cloud Deploy release or promote a release candidate directly. Its output is an eligibility signal that later deployment and trust enforcement steps can consume.

## MVP verification checks

The MVP should start with a minimal set of checks:

| Check | Purpose | Expected result |
| --- | --- | --- |
| Release metadata completeness | Ensure the release can be reviewed and traced | Required fields are present |
| Image digest presence | Ensure the artifact identity is immutable | Digest is recorded |
| Approved image location | Ensure the artifact came from the expected registry path | Image URI matches approved Artifact Registry location |
| Source revision presence | Ensure the release maps back to source | Commit SHA is recorded |
| Build identity presence | Ensure the producing identity is reviewable | Build service account is recorded |
| Basic manifest readiness | Ensure deployment input can reference the trusted artifact | Render path or substitution expectation is clear |

These checks are intentionally narrow. Additional scanning or policy tools can be introduced later after the trusted path is executable.

## Verification output

Verification should emit or update the release metadata contract with:
- `verification_status`
- `verification_timestamp`
- `image_digest`
- `trust_signal_ref`, when available

For the MVP, the verification result can be represented as a small JSON object that is written to build artifacts or emitted with consistent log keys:

```json
{
  "source_repository": "<repository-uri>",
  "commit_sha": "<commit-sha>",
  "build_id": "<cloud-build-id>",
  "build_service_account": "<cloud-build-service-account>",
  "image_uri": "<artifact-registry-image-uri>",
  "image_digest": "<sha256-image-digest>",
  "verification_status": "passed",
  "verification_timestamp": "<rfc3339-timestamp>",
  "trust_signal_ref": "pending-binary-authorization-attestation"
}
```

Use `verification_status=failed` for a candidate that does not meet the MVP checks. The failure output should keep the release identity fields populated when they are known, and it should not create or imply a deployable trust signal.

A failed verification should still preserve release metadata so operators can understand why the release candidate is not deployable.

## Trust signal preparation

For the MVP, verification should prepare the input needed for the minimal trust signal.

The trust signal should be tied to:
- the verified image digest
- the build that produced it
- the verification result
- the expected attestor or policy path, when implemented

The first version may document or emit this input before Binary Authorization attestation is fully automated. The important architectural rule is that the trust signal is derived from verification, not from the mere existence of an image.

## Governance handoff after verification

Verification output is an input to governance, not the final deployment decision. After verification finishes:
- trust enforcement evaluates deploy eligibility for the target environment
- deployment proceeds only through the explicit promotion path
- operators perform runtime review before allowing further promotion

This keeps the release path aligned with the rule: verify first, enforce trust, deploy with policy, then review before promotion.

## Failure semantics

Verification failure should stop the trusted release path before promotion.

A failed release candidate should not:
- be promoted to stage or prod
- receive a deployable trust signal
- be treated as equivalent to a verified artifact
- be silently replaced by a rebuilt artifact without a new release identity

## Non-goals for MVP

The MVP verification stage does not need:
- many security scanners
- custom policy engines
- complex provenance frameworks
- multi-attestor policy chains
- enterprise change management integration

Those capabilities can be added after the project demonstrates a clear verification-to-trust-to-deploy path.

## Related documents

- [Release Metadata Contract](architecture/release-metadata.md)
- [Trust Model](architecture/trust-model.md)
- [Environment Policies](architecture/environment-policies.md)
