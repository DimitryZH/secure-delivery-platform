# Adopt the selected Collector supporting image

Refs [#93](https://github.com/DimitryZH/secure-delivery-platform/issues/93).
This path is separate from application release #87. It never rebuilds, retags,
changes membership of, or reattests that accepted catalog release.

## Policy and proof

[`policy.json`](policy.json) is the only image/publisher input. The CLI accepts no
image, candidate, arbitrary key, mirror destination, verification-result or bypass
flag. It requires the selected official Collector Contrib repository, exact
workflow identity/issuer, linux/amd64 and the approved `otelcol-contrib` mirror.
Changing selection requires a separate reviewed policy change.

[`collector.py`](../../cloudbuild/online-shop/collector.py) verifies the exact signed
index with Cosign, unique linux/amd64 membership, actual manifest/config bytes and
platform, descriptor sizes and every compressed layer's bytes/hash. Mirror proof
independently reads and hashes the same content from Artifact Registry. External
layer URLs are rejected; public GHCR CDN redirects strip auth and have an explicit
HTTPS host allowlist. Registry digest addressing alone is not publisher proof.

Cosign 3.1.4 and crane 0.22.1 are pinned by platform/release SHA-256 in
[`collector-tools.json`](../../cloudbuild/online-shop/collector-tools.json).
The CLI downloads official GitHub release assets into an ignored private cache,
rechecks cached archives and extracted executable bytes, and never selects a
tool from PATH. Release-checksum integrity uses official HTTPS assets; no separate
binary provenance claim is made. Cosign uses its public Sigstore trust defaults,
exact identity/issuer, and normal certificate/transparency-log checks. Ambient
Cosign/Sigstore trust overrides and Docker credentials are isolated from that call.
No ignore-TLog, ignore-SCT, insecure TLS or custom trust-root switch is exposed.

Read-only verification can be run before merge:

```powershell
python -B cloudbuild/online-shop/collector.py publisher
if ($LASTEXITCODE -ne 0) { throw 'Publisher proof failed' }
```

On 2026-10-30 this command passed live for the unchanged policy index,
linux/amd64 manifest/config and all three layers. This does not establish mirror,
platform attestation or runtime acceptance. Raw proof/tool diagnostics stay private;
sanitized results are in [`validation.json`](validation.json).

## Subsequent live adoption — after merge and separate authorization

Do not execute the mutations below in the implementation review phase. Select a
full immutable merged-main SHA containing this code. Mirror, verify, inspect and
signing entry points independently fetch canonical main, require ancestry and
compare all executing trust files with that SHA. Feature code cannot execute under
the signer through this CLI; the read-only publisher action grants no exception.

```powershell
$configuration = '<FULL_MERGED_MAIN_SHA>'
python -B cloudbuild/online-shop/collector.py mirror --configuration-revision $configuration
if ($LASTEXITCODE -ne 0) { throw 'Stop and inspect private diagnostics' }
python -B cloudbuild/online-shop/collector.py verify --configuration-revision $configuration
if ($LASTEXITCODE -ne 0) { throw 'Mirror verification failed' }
python -B cloudbuild/online-shop/collector.py signing-request --configuration-revision $configuration
```

Review the generated request before separately authorized `submit-signing` with
the same revision. It uses only the existing regional Cloud Build API, exact Git
revision, existing attestation account, one verification/attestation step and a
900-second timeout. There are no candidate transports, image substitutions,
application build steps or mirror commands in the signing execution.

Mirror runs as the authorized existing operator with Artifact Registry write
access. `crane copy --jobs=1` copies only the pinned single-platform manifest to
the exact digest-addressed destination; no index/tag/all-tags copy or conversion
is requested. Destination manifest/config/layer readback must pass afterwards.
The OAuth token is passed to crane login by stdin, only for the approved registry,
in a temporary Docker config removed on exit. It is never a command-line token or
persistent login. A complete existing mirror is freshly verified and reused;
only an initial manifest 404 permits copying. Missing/corrupt blobs or denied
access to an existing image block the operation instead of overwriting it.

Inside Cloud Build, `attest` first confirms its metadata service-account identity,
then repeats live publisher, upstream content and mirror verification. Only then
can the existing KMS/note/attestor helper sign. The created occurrence is fetched
again and its exact URI, payload, digest, note, key and cryptographic signature
must pass before `status=trusted` is emitted. The result is `kind=supporting_image`,
never a new application release set. Existing signer grants are used unchanged;
the signer neither writes the registry nor acquires build-list permissions.

After the exact signing operation/build reaches terminal status, independently run:

```powershell
python -B cloudbuild/online-shop/collector.py inspect --configuration-revision $configuration
if ($LASTEXITCODE -ne 0) { throw 'Supporting image is not trusted' }
```

`inspect` repeats publisher/content/mirror verification and validates actual
occurrence/signature readback; it never signs. Build SUCCESS alone is insufficient.
Retain operation/build IDs, terminal status, trusted signer output and independent
inspection privately. Deployment `workflow.verify_support` reuses the same content
verifier and still requires a valid occurrence for the exact mirrored URI.

## Existing results and uncertain responses

Every signer run lists all attestation pages within a bounded limit, fetches and
validates matching occurrences and reuses valid results before invoking KMS.
Invalid existing proof fails closed. Unknown copy/create responses trigger only
read-only recovery checks, never an automatic second mutation. If recovery cannot
establish a result, stop and inspect remote state before deciding any further action.

Submission lists builds tagged for this purpose and exact configuration first.
It checks their execution shape and returns existing queued/running/terminal builds,
including failures, instead of creating another. An uncertain POST triggers a
read-only build lookup. Record the operation immediately; inspect the actual build
and occurrence before retrying. Serialize operators: occurrence creation has no
server-provided caller idempotency key, so this is not an exactly-once guarantee
against concurrent submissions or eventually consistent reads. A failed build is
not permission to resubmit, mutate IAM, weaken verification or replace the image.

## Prerequisites and limits

- Merge/review this implementation and select its full main SHA before mutation.
- Use existing caller build-create/list and signer actAs permissions; use existing
  operator registry write access for mirror. Missing access blocks execution; no
  IAM/Terraform change is included or implied.
- Recheck existing signer registry-reader, KMS signer, note attacher, occurrence
  create/get/list and attestor verification access without expanding scope.
- Network access to official tool releases, Sigstore, GHCR/CDN and approved Google
  APIs is required. Windows bootstrap and publisher proof are locally exercised;
  the Linux Cloud Build execution and live copy/signing remain unexecuted.
- Prior authorized infrastructure apply is recorded separately in validation.
  This change performs no infrastructure operation, mirror, signing or deployment.
- Collector runtime, WIF export, file permissions/rotation, native-linked telemetry,
  admission and preservation of sample-service remain later live acceptance.

Sources: [Cosign verification](https://docs.sigstore.dev/cosign/verifying/verify/),
[pinned crane copy implementation](https://github.com/google/go-containerregistry/blob/v0.22.1/cmd/crane/cmd/copy.go),
[Cloud Build query/tags](https://docs.cloud.google.com/build/docs/view-build-results#filter_build_results_by_using_queries),
[occurrence creation API](https://docs.cloud.google.com/artifact-analysis/docs/reference/rest/v1/projects.occurrences/create).
