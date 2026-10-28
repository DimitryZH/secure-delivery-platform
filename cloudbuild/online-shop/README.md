# Trusted catalog release creation

Implements the code path for [issue #87](https://github.com/DimitryZH/secure-delivery-platform/issues/87).
Live acceptance is **pending**, not established by these files or offline tests.
The existing sample-service build, metadata, verifier, signer and trigger are unchanged.
No deployment, rendering, preflight, Redis, Collector or telemetry infrastructure is included.

## Contract and identity

[`catalog-v1.json`](catalog-v1.json) is the environment-independent allowed profile:
exactly `productcatalogservice`, `linux/amd64`, canonical AML repository at
`89fd1cde8285761cc2a35dfb22d145adb2eed980`. The executable policy additionally
requires that exact profile; supplying a different JSON profile is not authorization.
Changing membership or the approved source requires a reviewed policy/version change.

[`candidate-v1.schema.json`](candidate-v1.schema.json) describes the candidate wire
format. The runtime gate is stricter than schema validation: it reconstructs the
entire expected record from trusted policy and independently obtained evidence.
Unknown properties (including environment, verification and signing claims), missing,
duplicate, unexpected or inconsistent component records are rejected.

`release_set_id` is `sha256:` plus the SHA-256 of the complete candidate **without**
`release_set_id`, serialized as ASCII JSON with sorted keys and separators `,` and
`:`. There are no timestamps or environment settings in the candidate. Component
order is deterministic (one member in v1). Source/configuration/build/plan/artifact
references are immutable identity inputs. The same candidate has the same identity
across environments; changing membership, digest or producing execution creates a
new candidate. Verification and signing results live in separate JSON documents
referencing that identity, so neither enters the identity calculation.

The candidate records:

- Full AML source SHA, separate SDP configuration repository/SHA/path and exact
  generated Cloud Build request hash.
- Canonical plan hash, COPY-expanded input-list hash, planner/contract content
  hashes and immutable Git reference. Hashes use Git blob bytes, not checkout EOLs.
- Regional Cloud Build resource name/ID and allowed producer service account.
- Artifact Registry repository, actual registry manifest digest, platform and
  image configuration digest. The latter is the image configuration identity,
  **not a separately observed local Docker image ID**. Local IDs and build logs
  are not accepted as registry publication evidence.

## Source to build to digest

`release.py` generates a small Cloud Build REST request, rather than extending the
sample trigger or introducing another infrastructure resource. The request uses
`source.gitSource` to fetch an exact SDP commit. It installs Git in the preparation
step, obtains AML objects from the canonical repository at the pinned SHA, loads
the planner from those same objects, validates its full contract, and checks its
canonical plan against the independently computed expected hash.

It materializes a new Docker context containing only the tracked COPY-expanded
inputs and Dockerfile/ignore controls. Each byte is checked against its plan hash;
the complete context is inventoried again. Existing destinations, extra files,
symlinks and byte drift fail. There is no AML working-tree checkout, host generation,
untracked-file copy or historical published-image substitution.

The only Docker build is the release contract invocation:
`--platform linux/amd64`, full `SOURCE_REVISION`, empty `SKAFFOLD_GO_GCFLAGS`, no
target and no preparation/regeneration. Cloud Build's `images` publication records
the pushed manifest digest in `results.images`; a failed publication fails the build.
The Docker step explicitly enables BuildKit for AML's Dockerfile cache mounts.

For verification, the live adapter reads the regional Cloud Build API and demands:

1. Exact project/resource/ID, successful terminal build and successful steps.
2. Exact source and `sourceProvenance.resolvedGitSource` identifying the selected
   SDP commit; exact producer, ordered steps/arguments, images, timeout and options.
   Added executable configuration, secrets, substitutions and dependencies fail.
3. Exactly the expected published image and digest from service-produced results.
4. Artifact Registry manifest bytes matching that digest; image-config bytes
   matching their digest; actual `linux/amd64` platform and expected revision label.
   Multi-platform indexes are deliberately unsupported in catalog-v1.

The verifier computes the AML plan again from canonical pinned objects. Exact
reviewed preparation/build steps connect those inputs to the Cloud Build result.
This does **not** misrepresent SDP source provenance as direct Cloud Build AML
source provenance. The AML association is established by those inspected steps,
their enforced hashes and successful execution. Labels, logs and supplied JSON
alone establish no provenance. Candidate creation and signing use the same gate.

Authoritative sources and assumptions:

- GitHub canonical Git objects and main ancestry establish reviewed configuration
  under the repository's human review model. Live commands require an explicit
  immutable configuration SHA reachable from current remote main and compare all
  executing trust files to that commit. No feature-branch override exists.
- Cloud Build API output and Artifact Registry digest-addressed bytes are trusted
  service evidence. Privileged cloud administrators, repository reviewers and
  execution infrastructure remain trust roots; this is not an independent SLSA
  attestation or a claim of resistance to a compromised build worker.
- Builder image tags, Debian package sources and AML's Go base tag/dependency
  resolution are not fully locked. This is repeatable input selection, **not**
  byte-identical rebuilding, a dependency audit or production approval.

See the pinned AML
[build](https://github.com/DimitryZH/application-modernization-lab/blob/89fd1cde8285761cc2a35dfb22d145adb2eed980/workloads/online-shop/docs/BUILDING.md),
[runtime](https://github.com/DimitryZH/application-modernization-lab/blob/89fd1cde8285761cc2a35dfb22d145adb2eed980/workloads/online-shop/docs/RUNTIME.md)
and [build acceptance](https://github.com/DimitryZH/application-modernization-lab/blob/89fd1cde8285761cc2a35dfb22d145adb2eed980/workloads/online-shop/validation/build/RESULTS.md)
contracts. Historical builds tested `4fd3795de94bd005b7b02b32c6b74abc8775b62c`;
later planner correction `cc2fada6d1baf9ed1571cfacbc8469221a82c1a3` has separate
regression evidence, not a new full build. Application/build-contract inputs are
unchanged in the selected SHA. Historical runtime evidence is not SDP live evidence.

## Separate signing

`signing-request` generates a separate Cloud Build request under the existing
attestation account. Executable source is the reviewed SDP Git commit. Candidate
JSON comes from a generation-pinned object in the existing dedicated attestation
source bucket; its transport SHA-256 is checked before parsing. Candidate bytes
cannot select executable code, profile, source policy or a supplied success result.

The signer independently re-fetches AML, re-computes the plan and queries Cloud
Build/registry again. Only then does it reuse the existing sample signer's KMS and
Binary Authorization simple-signing functions. It signs the verified manifest
digest, validates the signature before occurrence creation, reads the occurrence
back, matches subject/note/key/payload and validates its signature again.

`status=trusted` is emitted only after every required member has passed all those
checks. Any exception emits nonzero status with `trusted=false`, no partial trust
references and no raw diagnostics. A failure after creation may leave an occurrence;
inspect before retrying. The aggregate result links the release identity to
digest-bound signatures; the standard signature does not itself sign the aggregate
JSON envelope. No promotion/deployment authority follows from this result.

The release CLI does not change IAM. In addition to existing KMS/note/occurrence/
attestor and bucket access, independent verification requires `cloudbuild.builds.get`
and `serviceusage.services.use` in the configured project and Artifact Registry
download/read access scoped to the release repository.
[Catalog verification IAM](../../terraform/foundation/catalog-verification-iam.tf)
declares a custom role containing those two permissions and a repository-scoped
Registry Reader binding for the signer. Cloud Build IAM is project-scoped, so build-get can
read other builds in that project; it grants no list, submission or mutation access.
The service-usage permission satisfies the documented
[Cloud Build custom-role requirement](https://docs.cloud.google.com/build/docs/securing-builds/configure-access-to-resources#creating_iam_custom_roles);
it does not enable services.
These declarations require a separately reviewed plan and authorized apply, then
fresh effective-access checks. Configuration presence does not establish live access.
Do not grant builder signing, deploy, impersonation or policy-administration access.

## Operator usage after review and merge

Prerequisites: Python 3.10+, Git, existing authenticated gcloud; approved submitter
permissions and execution-account `actAs`. Inside Cloud Build the preparation and
signing steps use the SDK image's Python 3. Both live jobs fetch exact Git source.

First select a full reviewed configuration SHA on main **containing this code**.
Run from that clean immutable source. The CLI reads project/registry/producer from
the reviewed `deploy/environments.json`; region is explicitly `us-central1`, matching
the foundation defaults. Signer/key/note names reuse the existing foundation.
Inspect the generated request privately before any submission; confirm those targets
against the actual environment and effective IAM, never the active default project.

Offline plan inspection can read a local AML repository without changing it:

```powershell
python -B cloudbuild/online-shop/release.py plan --aml-repo C:\projects\ai\application-modernization-lab
```

After merge, privately set `$configRevision` to the reviewed full SHA. Generate and
review the build request, then submit **one** bounded build (1200-second timeout):

```powershell
python -B cloudbuild/online-shop/release.py request --configuration-revision $configRevision
python -B cloudbuild/online-shop/release.py submit --configuration-revision $configRevision
gcloud builds describe $buildId --project=$project --region=us-central1 --format='value(status)'
python -B cloudbuild/online-shop/release.py candidate --configuration-revision $configRevision --build-id $buildId
python -B cloudbuild/online-shop/release.py verify --configuration-revision $configRevision --candidate $candidatePath
```

`submit` returns an operation and, when available, build ID. Observe that operation
or exact build until terminal completion; do not blindly retry on an uncertain
response. Save candidate/verification stdout privately as UTF-8 JSON only after
checking exit status (the CLI emits a failure record on error). Do not redirect
failed output over a previously accepted candidate. Builds/downloads/storage incur
charges; this path creates no trigger, scheduled traffic or deployment.

For separate signing, the authorized operator stages **only candidate JSON** in
the dedicated source bucket with create-only generation preconditions. Record the
actual object generation and SHA-256 outside mutable object metadata; do not overwrite
or delete older evidence. Set `$candidateObject` to
`gs://<PROJECT_ID>-attestation-source/<unique-path>/candidate.json#<generation>`.

```powershell
python -B cloudbuild/online-shop/release.py signing-request --configuration-revision $configRevision --candidate-object $candidateObject --candidate-sha256 $candidateHash
```

Review the generated JSON, then have the authorized signing submitter create one
bounded signing build (600-second timeout):

```powershell
python -B cloudbuild/online-shop/release.py submit-signing --configuration-revision $configRevision --candidate-object $candidateObject --candidate-sha256 $candidateHash
```

Both submit actions call `projects.locations.builds.create` directly with the reviewed
request and explicit target project/region. They retain `source.gitSource`; do not
substitute a local source upload, candidate-controlled scripts or the image-build
identity. API compatibility remains part of pending live acceptance. Keep signing logs/results private
and copy only reviewed, sanitized outcomes into durable public evidence.

Cloud Build readback currently requires exact input field representations. A new
service default/serialization difference fails closed and must be inspected and
covered by a regression before support is added. It must not be bypassed with
supplied JSON, weakened comparisons or additional IAM authority.

## Checks and acceptance status

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:SDP_AML_REPOSITORY = 'C:\projects\ai\application-modernization-lab'
python -B -m unittest discover -s scripts/tests -p 'test_*.py'
git diff --check
```

The new tests use controlled API fakes plus real local pinned AML Git objects.
Main-only checks use disposable local Git fixtures. Sample regressions use local
loopback HTTP only. No mocks constitute live acceptance. See
[`validation.json`](validation.json) for sanitized results and pending criteria.

Cloud Build API source/result semantics:
[Build REST reference](https://docs.cloud.google.com/build/docs/api/reference/rest/v1/projects.builds).
Registry authentication:
[Artifact Registry access tokens](https://docs.cloud.google.com/artifact-registry/docs/docker/authentication).
