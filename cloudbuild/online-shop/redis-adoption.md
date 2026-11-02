# Redis dependency adoption for Online Shop

Prepare the reviewed route **Docker Official Image → canonical Docker Hub mirror → SDP Artifact Registry** for [#100](https://github.com/DimitryZH/secure-delivery-platform/issues/100). This change performs source/content inspection and local tests only. Mirror publication, signing and deployment are pending.

## Selection and source proof

The selected image is `docker.io/library/redis:7.4.12-alpine3.21`, a patch update within the existing Redis 7.4 runtime line. Tags are discovery metadata; all verification and copy references use immutable digests.

| Identity | SHA-256 |
| --- | --- |
| Official upstream index | `sha256:8da19c7399dca900c6822a1cf30f9d2285585e2c4b457ff4095b0f4500054d3f` |
| linux/amd64 platform manifest | `sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9` |
| Config | `sha256:98c6ca8f397f86e469be752c3e7ed5eb8b17f2479840cb69a2e413037038e9f4` |

[redis-policy-v2.json](redis-policy-v2.json) pins the official repository, immutable Docker Official Images metadata, Dockerfile/entrypoint source hashes and index-bound provenance. Metadata revision `72aa61399c17a658738763be8dbbf987880a7b2a` selects `alpine` at [`redis/docker-library-redis@786872f8c248c1f0990f93244cbcb3949329016d`](https://github.com/redis/docker-library-redis/tree/786872f8c248c1f0990f93244cbcb3949329016d/alpine). The official index binds a platform provenance statement to this exact manifest, Dockerfile source/material and build invocation `yfknsyfxvj00lki3zrdos7mff`.

The explicit trust basis is Docker Official Images metadata plus the digest-pinned Docker Hub `library/redis` publication. The BuildKit statement is **unsigned**; this verifier does not claim a verified publisher signature, reproducible rebuild, SLSA level or vulnerability-free image. It checks the complete recorded association and content rather than inferring source from a tag, version string or matching layer alone.

Read-only verification passed for index membership, metadata/source bytes, provenance subject/source/build/platform, actual manifest/config and **all seven layer hashes and sizes**. Existing images and tags are untouched. The expected canonical and SDP artifacts are:

- `docker.io/dmitryzhuravlev/online-shop-redis-cart@sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9`
- `us-central1-docker.pkg.dev/sre-platform-staging-507220/secure-delivery/redis-cart@sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9`

These are proposed references, not publication or attestation evidence. The previous image remains preserved; the prior immutable dependency policy is retained and is not an alternative admission path.

## Cross-repository contract

[AML Draft PR #27](https://github.com/DimitryZH/application-modernization-lab/pull/27) prepares the same canonical digest, config/version and runtime assertions. SDP pins dependency commit `23b5b28de59e73fbfe2d4eff027f33bd82ae5e26` and exact image/source/runtime/Compose/Kubernetes contract hashes. Production chain verification requires that exact commit to be on canonical AML main. The current branch correctly fails that gate before mirror/signing calls.

Application source and the ten component build plans remain pinned to AML `89fd1cde8285761cc2a35dfb22d145adb2eed980`; accepted catalog-v1 and Collector artifacts are unchanged. The frozen application runtime snapshot remains an input contract; actual rendered images always come from the newly reconstructed candidate. Redis source/build/index/contract references now participate in candidate identity. The complete profile hash changes with the dependency policy; stale candidates fail independent reconstruction. Candidate wire version 2 and exact eleven-member membership remain unchanged.

## Verification and admission

[redis.py](redis.py) exposes only read-only `upstream`, `canonical` and `chain` actions. It uses the existing checksum-pinned crane, isolated Docker auth configuration and approved repository set. Public upstream/canonical reads are anonymous; the approved registry receives its token via stdin in an ephemeral auth directory. Metadata URLs are closed to immutable approved GitHub source paths and redirects are rejected.

`chain` verifies merged AML contracts, repeats the official proof/content check, then independently hashes every config/layer in **both** the canonical and approved-registry copies. Wrong repository, missing mirror, source/build/subject/platform mismatch, unbound provenance, changed bytes, descriptor URLs, bad layer size/hash and inconsistent AML contracts fail closed. No missing-evidence exception, status flag or legacy digest can substitute for this chain.

The complete release verifier calls the chain before application evidence; the separate signer repeats that verifier before any attestation. Runtime/signals/journey remain guarded. Cleanup keeps its independent, local ownership/scoped-target checks from the reviewed cleanup fix. Policy eligibility alone never produces a verified/trusted release. Cloud Deploy READY and required occurrence/signature readback still need all actual evidence.

## Compatibility and local checks

Redis settings are unchanged: UID/GID 1000, read-only root, writable `/data`, one Recreate instance, memory-only carts with RDB/AOF disabled, 6379, 15-second shutdown and existing CPU/memory limits. Official server/CLI binaries are mode 0755; the entrypoint skips root-only ownership handling under UID 1000, and Kubernetes explicitly invokes redis-server. fsGroup/project-volume ownership remains necessary for `/data`.

Cartservice remains the same source and .NET cache package 9.0.11, using Redis hash fields/expiry operations and empty-protobuf clear semantics. Its endpoint, probes and application logic are unchanged. Native metrics attribution now uses exact Redis version 7.4.12 instead of an unresolved version placeholder; Collector remains the existing separately trusted image. No duplicate scraper is introduced.

Local source/reference/Compose and build-planner checks passed in AML. SDP tests include source/build/subject/index attacks with consistently recomputed hashes, config/platform/layer corruption, both mirror reads, no credentials on public reads, fixed auth host/stdin, unmerged-contract refusal, full-set identity and guard regressions, actual public-byte fixtures and native Collector configuration validation. The local Docker engine is unavailable: real Redis/cart add/read/quantity/clear, restart/outage/recovery and telemetry checks remain pending. Contract/static checks are not a new runtime acceptance result. See [complete validation](../../deploy/online-shop/complete-validation.json).

## Next separately authorized live sequence

1. Review and merge both PRs. Verify executing SDP trust files at an immutable merged main SHA and the pinned AML commit on main. Confirm existing copy/signing identities and access without changing IAM. Rerun `python cloudbuild/online-shop/redis.py upstream` and retain raw responses privately.
2. Inspect the exact canonical destination first. If the matching manifest already exists, verify and reuse it. If absent, use the pinned crane for **one digest-addressed platform-manifest copy**, source `docker.io/library/redis@sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9`, destination `docker.io/dmitryzhuravlev/online-shop-redis-cart@sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9`. Authenticate only with the existing canonical publisher access; never store credentials in Git. Do not rebuild, copy the index instead, overwrite an existing tag or delete an image. After an uncertain response inspect actual destination state before retrying.
3. Run `python cloudbuild/online-shop/redis.py canonical`; require source proof plus all actual canonical bytes. Only then perform the same bounded digest-addressed copy from canonical to `us-central1-docker.pkg.dev/sre-platform-staging-507220/secure-delivery/redis-cart@sha256:1cf73a2f04808e55a8bd2f5706c2aa0ebb0f71938f93deb7af79f48311cd5cb9` using existing approved publication authority. Reuse an existing matching result and recover read-only on uncertainty.
4. Run `python cloudbuild/online-shop/redis.py chain`. It must verify both mirrors plus merged contracts and upstream source/content. Save references and actual results privately; do not mark a copy trusted from copy success alone.
5. With a running isolated Linux Docker engine, run the AML Redis/cart native/real-cart/restart/outage/telemetry acceptance and exact project-scoped cleanup. Do not repurpose historical results for the new digest.
6. Continue the [complete application procedure](../../deploy/online-shop/complete-README.md): all component evidence → full candidate independent verification → generation/hash-pinned candidate object → separate signing build → every required occurrence/signature readback. Redis is signed only as an eligible member of the complete set; there is no new Redis-only bypass or relaxed attestor policy.
7. Fresh capacity/infra/artifact-protection checks, dev rollout and the complete shopping journey remain later reviewed stages. No live mutation is authorized by this document or its offline test results. Keep #100 open until acceptance review.
