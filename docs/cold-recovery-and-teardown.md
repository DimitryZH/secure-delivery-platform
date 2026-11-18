# Cold recovery and cloud-resource retirement

This is a preparation and review procedure. A recovery kit, a destroy preview, or
merging this runbook does **not** authorize deletion, signing, deployment, a live
restore, or removal of destruction protection. Keep worker capacity paused while
preparing it. Application data, runtime logs and monitoring history are excluded.

Use the [isolated foundation procedure](../terraform/foundation/README.md),
[baseline recovery gates](platform-baseline-recovery.md), and
[manual capacity procedure](gke-pause-resume.md). Environment IDs, operator details,
exact commands, raw plans and operational results belong in ignored private files.

## Minimal retained-project path

For the current scoped teardown, use the existing local kit. Do not create another
copy or encrypt it as part of this task. An independent copy is an optional operator
choice, not an execution gate for this approved scope. Accept the single-workstation
loss risk explicitly. Do not repeat general tests, full-project asset discovery or
checks of organization, billing, parent DNS and unrelated/default networking.

The minimum sequence is controller cleanup, Kubernetes-root destroy,
foundation-root destroy, and bootstrap-root destroy **last**. Preparation does not
authorize any of them. Generate a fresh full destroy plan immediately before each
approved phase, using existing isolation/freshness/execution guards and normal locking.
Review and apply that exact saved binary once; never replay a kit's old plan.

Before execution, review these narrow exceptions:

- Retain the project, human administrative bindings, organization, billing account,
  main domain/parent DNS, default/shared network and Google-managed service agents.
  APIs remain enabled under the existing `disable_on_destroy=false` declarations.
- Retain the existing KMS ring, signing key and enabled key version for this minimal
  same-project recovery path. This leaves the signing-version cost but avoids changing
  the pinned authority, destroying version 1 or requiring a new trust profile.
  Before foundation destruction, explicitly approve forgetting **only** the two
  retained `google_kms_key_ring.attestation` and `google_kms_crypto_key.attestation`
  state bindings with `terraform state rm`. This is intentional retention, not a
  way to delete a protected object. Do not run a normal apply after forgetting them;
  reimport both survivors before any future normal foundation plan. The full destroy
  plan must contain no action on the retained key/ring or key version. IAM grants
  for retired machine signers may be removed while the key itself remains.
- After explicit teardown approval, remove `prevent_destroy` only for the cluster and
  two pools before the foundation phase, and for the backend bucket only at the final
  bootstrap phase. Keep the KMS protection. This is a source-level gate; a fresh,
  complete plan remains required before any apply.
- Delete HTTPRoutes/Gateway and the frontend Service through Kubernetes first.
  Wait for the exact controller-owned load balancer/NEG/firewall resources to vanish
  while the cluster exists; never force-remove finalizers or resume workers silently.
- Release only the inventoried held object generations; empty the SDP source/render
  buckets including noncurrent objects after retention permits deletion. Do not enable
  `force_destroy` or weaken bucket retention/soft-delete policies. Empty and remove
  the backend only after both other roots have finished and no lock/operation remains.
- Cloud Deploy pipeline deletion may cascade to its archived releases through the
  locked provider. Name that cascade in the reviewed scope and ensure no active work;
  otherwise stop. Connection/repository/OAuth-secret and service-created source-bucket
  cleanup are explicit non-Terraform exceptions, restricted to recorded SDP IDs.

The short private command sheet must list those IDs, the four protection edits,
the two retained KMS state bindings, and the existing kit path. No project deletion,
blanket IAM cleanup, full-project scan or new environment profile is needed for this
retained-project path. Cold recovery uses the saved source/inputs, fresh backend
state for deleted resources, reimports the two retained KMS resources, imports the
unchanged image graph, and reestablishes saved attestations before a separately
authorized deployment. The longer sections below describe broader alternatives;
they are not additional gates on this minimal path.

## Recovery kit and offline checks

Store the kit outside the project that will be retired: a local private directory
or independently controlled storage with no dependency on that project's IAM,
KMS, registry or billing. Local storage outside GCP satisfies the location boundary;
it is not an independently tested off-site backup. For a broader disaster-recovery
scope, an operator can separately choose an encrypted independent copy and keep its
decryption material outside the archive. The minimal retained-project path above
explicitly uses the existing local kit without new copies or encryption.

Restrict access before collecting files. Raw Terraform state and inputs are secrets;
state can include short-lived provider tokens even when no credential file was
copied. Do not archive ADC files, SDK credential databases, GitHub OAuth token values,
service-account private keys or browser profiles. Reauthenticate during recovery.
Never commit, stage or upload the kit to a public PR or workflow artifact.

The private manifest must cover:

| Material | Required evidence |
| --- | --- |
| Git | Published release metadata, tag and peeled commit; complete SDP and canonical workload Git bundles; exact producing, deployment, validator and trust revisions; bundle verification |
| Terraform | Approved inputs/features/backend configuration, provider locks, generated-root manifest and source hashes, CLI versions; raw bootstrap and remote foundation/Kubernetes state with lineage, serial and object generation |
| State history | All available backend object generations and a current state pull; identify the current generation explicitly rather than selecting a historical state by filename |
| Images | Every retained image reference needed by candidates/releases, plus explicitly inventoried auxiliary images; original image indexes/manifests, every platform config and compressed layer, with descriptor sizes and SHA-256 checks |
| Trust | Attestation notes/occurrences, exact serialized signed payloads, signatures and public-key IDs, KMS public keys and version identities, Binary Authorization policy and attestors, verifier results and producer build metadata |
| Delivery | Candidate bytes, exact GCS generations/holds/retention, source and rendered bundles, Cloud Deploy pipeline/targets/releases/rollouts, selected runtime templates and immutable image bindings |
| Access and endpoint | Operator's project/organization/billing IAM baseline; service accounts and grants; API prerequisites; connection/repository/secret **metadata**; delegated DNS records, parent NS/DS baseline, certificate/address and controller-owned resource inventory |
| Operations | Paused capacity readback, inventory scope and gaps, private restore/teardown handoff, exact destroy previews and blockers; no application data or log/metric history |

An image name or digest without its bytes is not a backup. A Git bundle does not
contain registry layers, LFS objects, submodule repositories or release attachments.
Inventory these separately if present. A dependency fetched at build time is not
guaranteed to remain available; preserve existing deployable images rather than
claiming that a future rebuild will reproduce their digests.

`scripts/recovery-kit.py` provides read-only registry export and offline verification.
Its image inventory is a private JSON list of immutable Artifact Registry references.
Supply a short-lived registry token on stdin without logging or persisting it:

```text
python scripts/recovery-kit.py export-images --inventory <private-images.json> --output <kit>/images --token-stdin
python scripts/recovery-kit.py verify <kit>
```

The exporter retains original manifest bytes, recursively includes every platform,
deduplicates blobs, and validates SHA-256 and sizes. It refuses mutable tags,
foreign layer URLs and unexpected credential-bearing redirects. It performs no
registry writes. Exported OCI ref-name annotations preserve the original source
identity; copying to another registry still needs a separately reviewed import tool.

`kit-manifest.json` has `version: 1`, `required_images` (the complete immutable
reference list), and `files` mapping every relative file path to `size` and `digest`
(`sha256:<hex>`). It excludes only itself. The verifier rejects missing, additional,
redirected or corrupt files and traverses the complete OCI graph. Store the manifest
SHA-256 separately as a trust anchor; an editable manifest alone is not tamper proof.
Independently compare image coverage against candidates, render bundles, runtime
templates and signed occurrence payloads. Verify signatures offline against exported
public keys; compare GCS checksums and state generations. A successful hash check
does not prove that the input inventory was complete.

Do an offline reconstruction into an empty directory: verify both Git bundles,
resolve all pinned revisions, verify locks/source manifests, traverse all images,
and verify signed payload/image bindings. Record this as **offline validation**.
Until a separately authorized live restore succeeds, recovery time, quota, capacity,
external access and end-to-end recoverability remain unproven.

## Restore in the same retained project

1. Verify the independent kit copy and manifest anchor before authenticating.
   Reestablish the human operator through the existing organization and billing
   administrators/MFA recovery, then check project identity and billing linkage.
   Preserve their administrative assignments; do not replace authoritative IAM
   policies from a stale backup. Recreate narrowly scoped machine grants separately.
2. Determine what still exists. If resources survived, reconcile a copy of current
   state against readbacks; if the backend alone was lost, restore the latest
   verified state into a reviewed backend with locking. Preserve lineage/serial.
   Never push historical state over a surviving current backend or force-unlock.
   For a genuinely empty rebuild, start fresh state and import any intentional
   survivors through reviewed plans. Archived states describe old resources; they
   are not instructions to import nonexistent objects.
3. Bootstrap the new backend first, then cloud foundation, then Kubernetes
   namespaces using the new foundation's exact endpoint/CA outputs. Use approved
   isolated auth, root-specific TF_DATA_DIR/default workspace, read-only provider
   locks and freshness/execution guards before each fresh full plan/apply. Do not
   copy cached backend metadata or old SDK credentials into a new installation.
4. Review retained KMS key/ring names before creating them. KMS names and deleted
   service-account identities have reuse constraints; an identical email/resource
   name does not imply the same identity or trust. Current code selects a fixed
   signing key version: recovering a destroyed version requires a reviewed change
   to the key/version selection and all dependent bindings, not relabeling old keys.
5. Import saved image manifests/configs/layers into the reviewed registry without
   converting manifests. Read every destination digest back and verify the complete
   graph. Recreate source/protection objects from exact archived bytes under new
   generations and reviewed holds/retention; never reuse an old generation ID.
6. Reauthorize the GitHub App/connection and linked repository using an approved
   current GitHub administrator. Recreate regional secret versions by fresh OAuth
   authorization; metadata is not a saved credential. Confirm COMPLETE installation,
   correct repository/region and narrowly scoped access. Keep triggers absent or
   disabled until separately reviewed; reconnection must not launch builds.
7. Reestablish trust before workloads. Verify saved signatures offline. If the old
   key remains valid and the exact original image identity is retained, review
   whether archived occurrences remain admissible. Otherwise independently verify
   the recovered image/source/evidence and sign a new release with a new authority.
   Create new notes/occurrences/attestors and enforce the singleton policy before
   admitting workloads. Never bypass admission or manufacture a historical signer.
8. Recreate the delegated application DNS zone, address and certificate. The parent
   domain, registrar, portfolio/mail records and organization remain owned by their
   existing administrators. Update only reviewed child NS/DS delegation if needed;
   validate DNSSEC, TTLs, certificate authorization, SAN/chain and the new address.
   Do not assume the old public IP or child nameservers can be reclaimed.
9. Review a new protected render/candidate and new release identity, then authorize
   capacity and deployment separately. Fresh runtime/admission/HTTPS/telemetry and
   scheduled-monitoring acceptance are required. Redis starts empty. Historical
   release acceptance is evidence of the original environment, not of this restore.

## Restore in a new project

Use the preceding sequence with a new project ID/number, backend, KMS authority,
service agents/accounts, Workload Identity pool, registry URIs, connection, evidence
bucket generations and deployment targets. Do **not** copy old state into the new
project or use global string replacement on signed payloads or raw state.

The current environment execution guard and release/trust bindings are intentionally
project-specific. Prepare and review a new closed environment profile and regression
tests for the generator, backend guards, producer/verifier/signer identities, registry
allowlists, workload identities, candidate/render contracts, DNS and monitoring.
An environment-variable override is not an approved port of those guards. This
runbook does not silently make the current implementation project-agnostic.

Importing the original image graph can preserve its content digest, but a changed
registry path changes the signed Docker identity. Regenerate candidate and release
bindings, reverify provenance, and sign new payloads with the new KMS key/version.
Retain old signatures/public keys as historical evidence. A freshly signed replacement
must not claim the old producing build was executed in the new project. If the current
verifier requires live original build metadata that no longer exists, stop for a
reviewed offline-provenance import mechanism or separately rebuild/reverify; do not
relax the gate. Cloud Deploy releases and rollouts are new operations, not restored
historical IDs.

Cloud KMS does not export private signing material. Destroyed versions cannot be
recovered from public keys or signatures. New authority and repeat signing are an
expected part of cold recovery, with separate authorization for those mutations.

## Ordered teardown proposal

For the broader retirement alternative, require published-release identity, the
chosen recovery-copy policy, a reviewed inventory, an exact deletion allowlist and fresh
plans. Recheck operator/organization/billing/domain preservation at every phase.
The private deletion ledger must give actual resource IDs, state addresses, owners,
dependencies, retention/hold status and readback criteria. API pagination must be
complete. A disabled inventory API is a recorded gap, not proof of absence.

| Phase | Proposed work and gate |
| --- | --- |
| 0 | Freeze release/build/deploy work; verify paused pools, no active operations, kit completeness, independent copy, access recovery and exact deletion scope. |
| 1 | Separately authorize removal of application checks/alerts and the synthetic function/its service resources. A maintenance snooze does not stop checks or their costs. Do not turn expected pause failures into healthy evidence. |
| 2 | Remove application HTTPRoutes/Gateway and relevant policies/Services through the Kubernetes owner while the cluster and required identities still exist. Wait for controller cleanup of forwarding rules, proxies, URL maps, backend services, health checks, NEGs and related firewall rules. Inventory resources by identity/ownership, not a broad name-prefix deletion. |
| 3 | Reconcile finalizers and inspect controller logs/status without forced finalizer removal. If paused capacity prevents reconciliation, stop: a temporary resume requires a separate decision. Only after exact owned load-balancer resources are gone may namespaces and cluster be retired. |
| 4 | Retire Cloud Deploy releases/rollouts/pipeline/targets after active work is empty and their sources/renders are archived. Review the locked provider's force-delete behavior; never approve a broad cascade merely because Terraform generated it. Remove connection/repository and project-owned OAuth secrets separately; preserve the GitHub repository/account/App installation used elsewhere. |
| 5 | Delete namespaces with a fresh Kubernetes-root plan; then review removal of cluster/pool prevent_destroy and generate a new full foundation plan. Deletion protection and Terraform prevent_destroy are separate gates. Never use state removal or targeted destroy to bypass them. |
| 6 | Remove detached endpoint address/certificate/map, delegated child-zone records/zone, Armor/SSL policies and application networking. Preserve parent-domain registration, parent DNS/mail/portfolio records and unrelated/default/shared networking unless explicitly inventoried and authorized. Coordinate child delegation retirement with the parent owner. |
| 7 | Remove archived registry images, occurrences/notes/attestors, project-owned machine IAM/accounts and custom roles. Preserve human project/organization/billing administrative bindings. Deleting an impersonation grant on a retired machine identity must be distinguished from changing human administrative rights. Remove only project-owned secrets/connection resources. |
| 8 | Release only reviewed object generations' holds, wait for retention expiration, then empty all live/noncurrent objects and owned source/render buckets. Check soft-deleted versions and remaining retention/costs; never set force_destroy as a shortcut. Locked retention cannot be shortened. Include service-created source buckets/repositories outside Terraform. |
| 9 | After signature/access evidence is safe, separately review KMS version destruction and its waiting period. Key rings/crypto-key containers are not ordinary deletable resources. A provider state removal is not proof that their API resources disappeared. |
| 10 | Pull final states/checksums and operation results to independent storage. Delete the backend bucket **last**, after all other roots, pending operations, holds/retention and post-teardown reconciliation are complete. Bootstrap state is local; preserve it outside the bucket. Review its prevent_destroy separately. |
| 11 | Audit residual resources/costs with service APIs and an approved complete asset inventory. Existing declarations intentionally use disable_on_destroy=false, so enabled APIs can remain. Preserve operator, organization, billing account and parent domain. |

Fresh destroy previews must use the normal isolated guard, refresh and locking. Never
apply a saved pre-cleanup plan after controller deletion, namespace removal, hold changes
or state changes. Regenerate and review each phase. An exit-1 plan with prevent_destroy
errors is blocked even if Terraform leaves a binary file on disk; mark it DO NOT APPLY.
No destroy preview prepared by this procedure is authorized for execution.

### Retained project versus complete project retirement

Resource cleanup in a retained project allows later restoration with the same project
ID and preserves human project IAM. It can leave nondeletable KMS containers, enabled
APIs and service-managed/system resources. Do not call this literal zero-resource
deletion or guarantee zero cost while billable key versions/retention remain.

Project retirement is a distinct, separately authorized final option if literal removal
of project-contained resources is required. It must follow recovery verification and
controller/storage cleanup, and preserve organization/billing administrators and the
parent domain. It loses the project ID for reuse and removes project-local IAM with the
project; that conflicts with an unconditional requirement to preserve project-local
rights. Resolve this explicitly at review. A later rebuild then uses a **new** project;
project undelete windows are not the recovery strategy. Do not unlink billing or delete
the organization, billing account, registrar account or main domain.

## Review outcome

The private report states what was actually saved and verified, exact kit location and
manifest anchor, plan counts and blocked protections, inventory/access gaps, external
copy status, current paused state, retained costs, and the decisions needed for deletion.
Keep offline verification, planned restoration and executed restoration distinct. Do
not report a successful live recovery or completed teardown before they occur.

References: [KMS key material and resources](https://docs.cloud.google.com/kms/docs/resource-hierarchy),
[KMS destruction lifecycle](https://docs.cloud.google.com/kms/docs/destroy-restore),
[Gateway lifecycle](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/deploying-gateways),
[project deletion and identity reuse](https://docs.cloud.google.com/resource-manager/docs/delete-restore-projects).
