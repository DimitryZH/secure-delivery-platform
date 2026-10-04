# Cloud Deploy promotion foundation

```text
Verified artifact → Trust → Cloud Deploy → Binary Authorization → GKE target namespace
```

Cloud Deploy orchestrates progression of an already verified, attested digest.
It does not verify the build, sign attestations, or decide runtime admission.
Binary Authorization remains the admission authority on the existing GKE cluster;
the attestor, policy, and enforcement mode are unchanged. Build and deployment
authority remain separate.

## Declarative control plane

`terraform/foundation/clouddeploy.tf` defines the Cloud Deploy API, one
`sample-service` delivery pipeline in `us-central1`, and three targets in serial
order: `dev → stage → prod`. Every target points to the existing
`projects/sre-platform-staging-507220/locations/us-central1-a/clusters/secure-delivery-platform`
cluster. Pipeline profiles select the corresponding namespace in rendered
manifests; GKE targets themselves have no namespace field. Stage and prod require
Cloud Deploy rollout approval, consistent with existing environment review
requirements. Preparation review does not approve a Cloud Deploy rollout.

Both RENDER and DEPLOY explicitly use `secure-delivery-deploy`, never the build
identity or default Compute Engine identity. The only new IAM member is
`roles/clouddeploy.jobRunner` on that deployment account. Its existing
`roles/container.developer` and logging access are retained. No release creator,
promoter, approver, build-identity impersonation, or signing permissions are added.

The foundation assumes normal same-project Google-managed Cloud Deploy and Cloud
Build service agents retain their automatically provisioned service-agent roles.
It does not manually create or grant these agents, nor add cross-project access.
Before separately authorized execution, confirm effective service-agent IAM and
the caller's scoped release/promotion permissions and `actAs` permission on the
deployment account. Existing operator Token Creator access alone is not Cloud
Deploy release/promotion authorization.

Default Cloud Build workers and a dedicated custom artifact bucket are used. A future
release can cause storage and execution costs; this configuration creates
no release or execution jobs. The documented job-runner role includes
project-scoped storage object access; review effective access before apply.
It is granted only to the already separate deployment identity. Namespace mapping
is routing, not new namespace-scoped RBAC; existing cluster access is preserved.
See Google's [execution environment](https://docs.cloud.google.com/deploy/docs/execution-environment)
and [service account requirements](https://docs.cloud.google.com/deploy/docs/cloud-deploy-service-account).

## Source and rendered artifact protection

Related to #59. Terraform defines `sre-platform-staging-507220-clouddeploy`
in `us-central1`, using STANDARD storage, uniform bucket-level access and enforced
public access prevention. Object Versioning is disabled and `force_destroy=false`.
An unlocked bucket retention policy prevents object bytes from being replaced or
deleted for 86400 seconds. Administrators with bucket-update permission can change
this policy; it is not an irreversible retention lock.

Each target's RENDER/DEPLOY execution configuration uses
`gs://sre-platform-staging-507220-clouddeploy/rendered/<target>`.
The bucket reference creates the required Terraform dependency. This setting does
not configure source staging. A separately authorized release command must use
`--gcs-source-staging-dir=gs://sre-platform-staging-507220-clouddeploy/source/<release-name>`.
Prefixes organize objects; they are not IAM boundaries.

The release caller uploads source; the existing deploy identity reads it and
writes/reads execution outputs through Cloud Build. Google-managed service agents
retain their existing service-agent bindings. Existing grants cover these paths;
no new IAM bindings or project-wide storage roles are introduced. The build
identity's existing Cloud Build builder role already includes project-level GCS
object access. Bucket IAM cannot revoke inherited access, so retention protects
bytes during execution without granting the build identity deployment authority.

Use unique object names and record a SHA-256 hash of the actual archive outside
object metadata. Upload the original archive with a create-only generation
precondition. The installed gcloud SDK copies a GCS source archive to a new
timestamp/UUID staging object; verify the actual source URI recorded in the release
and its bytes, generation and retention expiration. Do not assume the release URI
pins an object generation. Before dev rollout, verify rendered digests, namespaces
and release annotations. Finish the initial render/dev validation within the
24-hour protection window; stop if the remaining window is insufficient.

Lifecycle cleanup deletes live objects after seven days, with a further seven-day
soft-delete recovery period. **This is an MVP storage-lifetime choice, not a
permanent promotion deadline.** Later promotions, retries or rollbacks require
review if artifacts have expired or their protection window has elapsed. Do not
assume an old release remains executable after cleanup. Retention compatibility
is supported by the documented Job Runner create/get/list permissions, but live
render/retry behavior still requires separately authorized validation. Stop on
retention-related write failures rather than relaxing protection automatically.

Release creation renders manifests for all serial targets. Use
`--disable-initial-rollout`, inspect all outputs, then separately authorize only
the dev rollout. Stage/prod rendering does not authorize rollouts, promotions or
workload changes. Digest-pinned raw manifests can be used without `--images` or
`--build-artifacts`; preserve the exact verified image identity and check the
rendered output before deployment. Storage protection does not replace artifact
verification, attestation or Binary Authorization admission.

See [retention policies](https://docs.cloud.google.com/storage/docs/using-bucket-lock),
[object lifecycle](https://docs.cloud.google.com/storage/docs/lifecycle) and the
[release command](https://docs.cloud.google.com/sdk/gcloud/reference/deploy/releases/create).

## Offline release preparation and rendering

`prepare-release.py` reuses `deploy/deploy-release.py` validation, the existing
`deploy/environments.json` policy, and both base manifests. It prepares three
target-specific views of one release without changing source, build, image digest,
verification, trust reference, or deployment authority. Only target namespace,
environment annotation, and APP_ENV vary. The input's original target is checked
first. Every target is validated before writing, and an existing bundle is never
overwritten. Preparation makes no subprocess or cloud call.

From the repository root, with verified metadata and an absent output directory:

```shell
python deploy/clouddeploy/prepare-release.py --metadata /local/verified-release.json --reviewed --output-dir .local-validation/bundle
cd .local-validation/bundle
skaffold diagnose -f skaffold.yaml -p dev --yaml-only
skaffold render -f skaffold.yaml -p dev --offline=true --digest-source=none --output ../render-dev.yaml
```

Repeat diagnosis and render for `stage` and `prod`. Run from the bundle directory
because Skaffold resolves raw manifest paths from the working directory. Use an
empty local kubeconfig for offline checks; no cluster context or credentials are
needed. Skaffold v2.13.2 was used to validate `skaffold/v4beta7`. The configuration
contains no build stanza, image substitution, hooks, or external exposure. The
existing Service defaults to ClusterIP.

Although `--digest-source=none` accepts general raw manifests, this preparation
path rejects tagged images and requires the verified `image@sha256:<digest>`.
Do not pass image overrides or substitute tags when integrating a real release.
All ten existing release annotations survive local Skaffold rendering. Generated
bundles and plan evidence stay ignored because real metadata can be private.
Synthetic examples support offline validation only; they are not trust evidence
and must never be submitted as a release.

## Plan review and later work

Use only the existing backend bucket
`sre-platform-staging-507220-tf-state` and prefix
`secure-delivery-platform/foundation`. Supply the existing project and operator
principal privately and generate a fresh locked plan:

```shell
terraform -chdir=terraform/foundation fmt -check
terraform -chdir=terraform/foundation validate
terraform -chdir=terraform/foundation plan -input=false -lock=true -lock-timeout=60s -out=/local/issue57-locked.tfplan
```

Review every planned change before any separately authorized apply. Stop if
unrelated drift appears. Do not reuse older plans, manually enable APIs, or apply
this foundation as part of offline validation.

Later Milestone 4 issues must define the controlled release handoff, verify live
trust evidence and effective IAM, assign reviewed release/promoter/approver
authority, and validate actual rollouts and same-digest promotion. Editing a raw
manifest outside preparation is not verification; the later handoff must protect
bundle integrity and correlate Cloud Deploy release identity with the metadata.
No release, rollout, promotion, workload, runtime validation, automated rollback,
or observability-based promotion is implemented here.
