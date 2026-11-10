# Manual GKE pause and resume

The separately managed foundation pools support a reviewed, manual capacity mode.
Terraform remains the only writer of node counts; no schedules or additional IAM
identities are needed. This procedure applies to an existing single-zone cluster
using `gke_create_separate_default_pool=true`.

| Private input `gke_capacity_mode` | default-pool | shop-dev-capacity |
| --- | ---: | ---: |
| `running` | 1 node | 1 node |
| `paused` | 0 nodes | 0 nodes |

Keep the selected mode explicitly in the environment's approved, ignored
foundation var-file, outside generated roots. Separate-pool plans fail if the
mode is omitted or null; unsupported strings fail validation. There is no implicit
pause or implicit resume. Historical combined-root adoption keeps its default
pool's `node_count=null` and the shop pool at one node; `paused` is rejected there.
The cluster's create-time sizing and temporary-pool removal sequence are unchanged.
Do not use this mode to bootstrap an empty environment or extend it to multiple
zones without reviewing the per-instance-group sizing semantics.

## Before each transition

Read the private environment instructions for the approved project, identities,
absolute input/backend paths and root-specific `TF_DATA_DIR`. Use the existing
foundation backend and default workspace. Regenerate with
`python scripts/prepare-greenfield.py`, verify with `--check`, and run
`--check-execution foundation` immediately before every plan/apply in the same
isolated process. See the [foundation execution procedure](../terraform/foundation/README.md#isolated-execution-roots).

Check current pool identities, actual sizes, node readiness, autoscaling and node
auto-provisioning, and active GKE operations. Both capacity mechanisms must remain
disabled for this manual mode. Check all namespaces, including system namespaces,
for Pods/controllers, Jobs/CronJobs, standalone Pods, PDBs, shutdown grace periods,
admission webhooks, volumes and local storage. Inventory ingress/Gateway,
LoadBalancer services and cloud load balancers/addresses. Check builds, releases,
rollouts, uptime checks, alert policies and scheduled synthetic checks. Stop for
unresolved work or unexpected ownership; absence of an application does not mean
the cluster has no workloads. These are operational prerequisites, not cloud
checks performed by the Terraform mode validation.

## Pause

1. Confirm the outage window and accept loss of ephemeral data. Finish or stop
   dependent work through its own reviewed procedure. Review monitoring behavior;
   pause does not suspend CronJobs, alerts or synthetic checks.
2. Change `gke_capacity_mode` to `paused` in the **same approved private var-file**.
   Keep it there throughout the pause. Record its hash and the generated manifest
   with the private plan evidence. Do not use a transient `-var` override as the
   operational selection.
3. After the freshness/execution guard, generate a new **full foundation plan**
   with that absolute var-file and a new private output filename. Use normal
   refresh and locking. Never target individual pools or bypass drift checks.
4. Review the plan's `variables.gke_capacity_mode.value` and every resource change.
   From the running baseline, expect exactly two in-place updates, only
   `node_count: 1 -> 0`, at `google_container_node_pool.existing_default` and
   `google_container_node_pool.complete_shop`. Expect zero creates, deletes,
   replacements or imports. Stop for any other change.
5. Apply only after explicit authorization of that exact saved plan and input
   provenance. Verify both pool sizes and managed instance group targets are zero,
   no worker VMs remain, and no conflicting GKE operation is active. Run a fresh
   full control plan with the persisted `paused` input; expect no changes.

For a plan-only preview, use a clearly labeled private copy of the full var-file.
This does **not** activate pause. Preserve the operational selection and record
that the preview is not authorized for apply. Before the actual first pause,
update the approved file and create a new plan.

## Resume

1. Recheck authentication, state/backend access, APIs, billing, current GKE status,
   quotas and zonal machine availability. Quota does not reserve capacity.
   Confirm node service account permissions, network/IP capacity, image access,
   valid trusted artifacts/attestations, storage attachment and workload prerequisites.
2. Set `gke_capacity_mode = "running"` in the same approved private file. Generate
   and review a **new full plan after the actual pause**, expecting only both
   counts `0 -> 1`. A running plan made before pause is not a recovery plan.
3. After separate apply authorization, apply the reviewed plan. Verify both nodes
   Ready, expected system controllers/DaemonSets, DNS, metrics, storage and workload
   health. Check Jobs/CronJobs for missed executions or backlog. Run a fresh full
   running control plan; expect no changes. Workload readiness is a separate gate
   from node creation and Terraform completion.

Never replay an old plan or switch var-files for an ordinary apply. All subsequent
foundation operations must use the persisted selection and review it against the
plan variables and input hash. Omitting the mode fails for separate pools, but an
explicitly supplied wrong mode still requests a real transition. A partial or
failed transition requires fresh read-only inspection and a new full plan; do
not blindly retry or resize with another tool.

## Availability, data and cost

With zero workers, applications and node-hosted system services (including DNS,
metrics and log collection) are unavailable. The control plane and Kubernetes
objects/namespaces remain; controller-managed Pods can recover after workers
return, while standalone Pods have no automatic recovery guarantee. Cluster,
pool identities, machine types, node identity, metadata mode and surge settings
are preserved. Trust policy, IAM and destruction protections are unchanged.

Node removal discards memory, container writable layers, `emptyDir`, node-local
logs, `hostPath` and local-disk data. Inspect the actual data paths and arrange
backups or accept loss before pause. Persistent volumes and external storage are
retained by resizing, but durability, reclaim policies and application-consistent
recovery still require review. A cached image or local candidate file is not an
image-layer backup. PDBs do not guarantee availability with no workers. GKE
[resizing documentation](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/resizing-a-cluster)
describes drain, best-effort shutdown and bounded PDB/grace-period handling;
account for this in the transition window.

The [pinned provider's default update timeout](https://github.com/hashicorp/terraform-provider-google/blob/v5.45.2/google/services/container/resource_container_node_pool.go)
is 30 minutes, while GKE documents PDB/grace-period handling for up to one hour.
A timeout can leave an operation running. Inspect GKE and state before replanning;
do not assume a timeout rolled back a resize.

This reduces worker compute costs; it does not make the environment free.
[GKE pricing](https://cloud.google.com/kubernetes-engine/pricing) includes a cluster
management fee independent of worker count, with eligible billing-account credits.
Retained persistent disks/snapshots, static addresses, load balancers, registry
images, object/state/evidence storage, KMS/Secret Manager and logging/monitoring
can continue to incur storage or usage charges where provisioned. Builds and
other managed services are not stopped by this mode. Node boot disks and ephemeral
addresses should disappear with their VMs; verify actual cleanup and billing.
Resume time and capacity are not guaranteed, and automatic GKE maintenance may
still occur while the control plane is retained.

The [locked Google 5.45.2 provider documentation](https://github.com/hashicorp/terraform-provider-google/blob/v5.45.2/website/docs/r/container_node_pool.html.markdown)
defines pool `node_count` per instance group and warns against combining it with
autoscaling. Complete teardown/recreation and lifecycle decomposition are separate
future work.
