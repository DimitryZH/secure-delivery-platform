# Binary Authorization admission

Related to #49. This change prepares enforcement; it has not been applied.

## Scope and policy

`terraform/foundation/binary-authorization.tf` adopts the existing project
singleton policy through a declarative import. Import and update occur only on
an authorized apply. The policy has one cluster rule for
`${gke_location}.${gke_cluster_name}` (currently
`us-central1-a.secure-delivery-platform`):

- `REQUIRE_ATTESTATION` by `projects/sre-platform-staging-507220/attestors/secure-delivery-verification`.
- `ENFORCED_BLOCK_AND_AUDIT_LOG`, not audit-only mode.
- `global_policy_evaluation_mode = "ENABLE"` for Google-maintained system images.
- No custom image allowlist or namespace bypass.

The cluster enables `PROJECT_SINGLETON_POLICY_ENFORCE` after the policy is
configured, in place. All application namespaces on this cluster, including
**dev, stage, and prod**, receive the same admission gate. The existing
`ALWAYS_ALLOW` default is retained for other clusters, outside this change's
protection boundary.

Application manifests must use `image@sha256:<digest>` from the verified release
record. The Issue #45 signing path only attests successfully verified digest
subjects, using authority separate from the builder. Admission checks the
attestation signature for the image digest; it does not rerun metadata
verification or separately enforce promotion, registry location, or Kubernetes
image-reference syntax.

## System workloads and permissions

Use Google's maintained system policy rather than exempting namespaces or
registries. Its exceptions apply by image identity, including outside system
namespaces; placing an arbitrary application in `kube-system` does not exempt
it. Custom platform images outside this policy also require the attestor.

Read-only inspection on October 1, 2026 found 15 Pods in `kube-system`,
`gmp-system`, and `gke-managed-cim`, with 37 distinct container/init-container
image references. All 37 matched the live system policy exception
`us-central1-artifactregistry.gcr.io/gke-release/gke-release/**`.
No application Pods were present. This check does not prove post-enable
admission or future custom platform workload compatibility.

The existing service agent
`service-465837787797@gcp-sa-binaryauthorization.iam.gserviceaccount.com` already
has `roles/binaryauthorization.serviceAgent` in this project. Read-only role
inspection confirmed attestor verification and note/occurrence read permissions.
No additional IAM, signing, API, or build-authority grants are needed.
Cross-project attestors would need separate permission review.

## Preparation evidence

Before this change the cluster returned an empty `binaryAuthorization` config;
the project policy had `ALWAYS_ALLOW` and global system-policy evaluation enabled.
Terraform formatting and validation pass with the existing provider lock.
The fresh state-locked plan was generated with:

```sh
terraform -chdir=terraform/foundation plan -input=false -lock=true -lock-timeout=60s -no-color -out=issue49-20261001-locked.tfplan
```

Result: **1 to import, 0 to add, 2 to change, 0 to destroy**:

| Resource | Action |
| --- | --- |
| `google_binary_authorization_policy.application` | Import existing singleton and update in place with the cluster attestor rule |
| `google_container_cluster.platform` | Enable Binary Authorization enforcement in place |

Plan JSON contains no resource drift or unrelated changes. Saved-plan checks
confirmed the exact cluster, attestor, enforced mode, enabled global system
policy, and absence of custom allowlists. Local plan SHA-256:
`6ebb0e0b53c207d878ff77290bf605131e63fe0e02f5e04fd1301864fa45f92b`.
The binary plan and full evidence stay in ignored local paths; plan JSON can
contain sensitive provider values and must not be committed. No apply, workload
deployment, live signing, or GCP resource mutation was run.

## Validation after a separately authorized apply

Export the effective policy and describe the cluster; confirm the rule and
`PROJECT_SINGLETON_POLICY_ENFORCE` match the reviewed plan. After deployment
authorization, test a digest-pinned application with the existing verified
attestation and another real registry digest without that attestation. Use
fresh Pod requests in a protected namespace, without break-glass annotations.
Require trusted admission and untrusted rejection by Binary Authorization;
record errors/events, Pod identity, digest, and effective policy. Inspect system
Pod health and replacements too. Live admission positive/negative checks are
pending, not claimed here.

Enforcement affects new admission requests; it does not evict existing Pods.
Unsigned application replacements and unsigned third-party sidecars will be
blocked. Google-managed exceptions and explicitly requested break-glass
overrides are trust-boundary limitations; do not use break-glass to pass the
validation. Disabling enforcement or changing policy needs a separate reviewed
change. Additional/future clusters need explicit protection.

References: [Google-maintained system images](https://docs.cloud.google.com/binary-authorization/docs/key-concepts#google-maintained_system_images),
[single-project permissions and enforcement](https://docs.cloud.google.com/binary-authorization/docs/getting-started-cli),
[system policy API](https://docs.cloud.google.com/binary-authorization/docs/reference/rest/v1/systempolicy/getPolicy).
