# Release Model

## Release identity

A candidate connects expected source, producing build, immutable image, verification, and attestation. A commit identifies source; a digest identifies image bytes; build ID and build identity identify execution. Promotion preserves them. A new digest is a new candidate that must re-enter verification and signing. Tags are not promotion identities.

## Metadata contract

| Canonical key | Meaning / producer |
| --- | --- |
| `source_repository` | Build context in `owner/repo` form |
| `commit_sha` | Full source revision |
| `build_id` | Producing image build ID |
| `build_service_account` | Producing execution identity; public `<BUILD_SERVICE_ACCOUNT>` |
| `image_uri` | Approved registry image reference |
| `image_digest` | Lowercase `sha256:<digest>` |
| `artifact_identity` | Successful verifier output: image without tag plus `@sha256:<digest>` |
| `verification_status` | `passed` or `failed` |
| `verification_timestamp` | UTC verification completion time |
| `errors` | Verification diagnostics |
| `trust_signal_ref` | Digest-bound attestation occurrence reference |
| `release_name` | Cloud Deploy release name when present |
| `target_environment` | Deployment target context |
| `promotion_state` | Progression context obtained from rollout state/operator review |

The first six fields are required build metadata. The producer emits JSON to build logs; automated persistence and transport are not implied. Verification emits a new record. Trusted deployment requires passed verification, timestamp, canonical artifact identity, and trust reference. Attestation returns fresh verification and its occurrence reference. Cloud Deploy supplies release/rollout state; not every script emits every lifecycle field in one JSON object.

A tagged initial URI may be verified with a consistent digest, but deployment requires the canonical pinned identity. Failed verification preserves known identity and diagnostics, omits `artifact_identity`, and must not produce deployable trust.

Optional fields include `build_log_url`, `artifact_registry_location`, `deployed_namespace`, `deployed_at`, `runtime_version_label`, and `operator_review_status`. No custom release database is required. Annotations and rollout resources are not a long-term audit store.

## Annotation mapping

Records use snake_case. Kubernetes uses `release.secure-delivery.dev/` with these suffixes:

| Record/context | Annotation suffix |
| --- | --- |
| `source_repository` | `source-repository` |
| `commit_sha` | `commit-sha` |
| `build_id` | `build-id` |
| `build_service_account` | `build-service-account` |
| `image_digest` | `image-digest` |
| `verification_status` | `verification-status` |
| `verification_timestamp` | `verification-timestamp` |
| `trust_signal_ref` | `trust-signal-ref` |
| `target_environment` | `target-environment` |
| Deployment execution identity | `deployment-authority` |

The shared Pod template carries these ten annotations. Inspect actual resources rather than assuming every annotation exists on every object. Cloud Deploy release annotations additionally correlate full commit, image build ID, immutable digest, trust reference, verification timestamp, archive SHA-256, and metadata SHA-256. The direct consumer does not fabricate a Cloud Deploy release name.

## Trust boundaries

The builder publishes an image. A separate signer reruns verification and signs the digest. Signing source, configuration, and submitters are trusted: arbitrary-code execution as the signer can bypass a script gate. Build authority must not gain signing, deployment, or privileged impersonation authority.

Verification proves metadata syntax and consistency, not artifact existence, producer provenance, source authorization, or tag-to-digest binding. Attestation certifies that specific gate, not stronger claims. Claimed status/reference fields are not cryptographic proof. Binary Authorization validates signatures at GKE admission; Cloud Deploy neither signs nor replaces admission. Runtime health does not replace pre-deployment trust.

## Promotion semantics

The serial pipeline is `dev → stage → prod`. Dev requires explicit initial rollout authorization. Stage and prod require explicit promotion and separate approval. Successful deployment never automatically authorizes the next environment.

Source, image build, verification, trust reference, and digest stay fixed; namespace, environment annotation, and `APP_ENV` vary. Preparation `--reviewed` is an operator assertion, not authenticated Cloud Deploy approval. Rollout state is progression context, not artifact identity. Hold or reject insufficient evidence. Rollback and corrective mutations need separate authorization and are never automatic.

See [Trusted Delivery](../trusted-delivery.md), [Environment Policies](environment-policies.md), and [IAM Model](../iam-model.md).
