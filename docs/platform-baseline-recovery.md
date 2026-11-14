# Platform baseline recovery gates

Restore and validate the accepted baseline before advancing the [roadmap](roadmap.md).
Recorded success describes its original execution only. Resource presence, node readiness
and a historical rollout do not establish current application or operational acceptance.
Use the reviewed active binding; keep operator identities, inputs, raw evidence, saved plans
and transport files private. This procedure does not authorize apply or deployment.

## Preserve the running workload

1. Read the completed resume result and control-plan outcome; do not repeat infrastructure
   operations or create another application deployment merely because nodes were replaced.
2. Inspect controllers, Ready/Available Pods, actual imageIDs, annotations, endpoints, DNS,
   workload identity, admission and per-node requests. Run the normal independent guard.
3. Use bounded internal GET smoke checks for read-only review. Redis DBSIZE/INFO are
   read-only; do not flush or rewrite carts. A full checkout needs explicit bounded traffic
   scope, its own session record, exact-key cleanup and owned port-forward cleanup.
4. Observe fresh traces, native-linked logs and metric points with source/version/release
   attribution. Report exactly which components the traffic exercised. Do not label a
   browse-only trace as full checkout acceptance or infer zero errors from missing data.
5. If a validator fix is needed, review and merge it first. Recheck the existing candidate
   with separate producing, deployment and validator revisions; preserve all signing and
   admission proof. A validator change alone does not require a rollout or new artifacts.

Runtime-only autoscaler diagnostic handling is described in the
[complete workload procedure](../deploy/online-shop/complete-README.md#existing-workloads-after-a-manual-node-resume).
Missing/unknown metadata still blocks acceptance. Never remove live annotations to pass.

## Staged cloud change proposal

These are dependency-ordered resource sets, not an applied plan or asserted Terraform
counts. Review a fresh full saved plan before each apply. Existing node pools, human
administrative grants, trust identities, registry artifacts and evidence holds are preserved.

| Stage | Resources and ownership | Required result before continuing |
| --- | --- | --- |
| Sample baseline | Existing sample Cloud Build trigger; one verified image/metadata and separate signing if absent; existing sample Cloud Deploy pipeline/targets | Same new-registry digest/signature promoted to dev/stage/prod with required approvals; Ready/Available and HTTP health in all three |
| Endpoint foundation | Foundation state: `google_project_service.shop_edge`, global address, child DNS zone, two DNS records, Certificate Manager authorization/certificate/map/entry, SSL policy and Armor policy from `shop-endpoint.tf` | Reviewed full plan; ten non-API resources plus three API ownership records if not already managed; no node-pool or unrelated changes |
| DNS/TLS | Operator changes only the reviewed child delegation/authorization at the actual external DNS provider | Actual assigned nameservers, authoritative/public DNS, no conflicting AAAA/DS, appropriate CAA, unchanged parent website/mail, certificate ACTIVE |
| Endpoint workload | Cloud Deploy owns Gateway, two HTTPRoutes and three policies; Gateway controller owns ALB/NEGs/forwarding/backend resources | Protected release/server render of 45 resources, fresh preflight and separate rollout authorization; observed-generation Gateway readiness, healthy frontend backend and valid HTTPS/HTTP301 |
| Endpoint protection | Existing Armor policy rules: priority100 probe, priority1000 WAF, priority2000 throttle1200/60s/IP | Fresh allowed/denied preview evidence, separate enforcement plan/apply; bounded actual403/429 proof with rule/log attribution; temporary test rules removed |
| Dashboard | Existing `google_monitoring_dashboard.online_shop_dev`, six reviewed PromQL queries and the existing Collector exporter path | Fresh query results for a bounded checkout, native trace/log linkage, probe exclusion, zero-versus-no-data and single ingestion through the existing Collector-to-Cloud-Monitoring path/PromQL bridge; no duplicate scrape path |
| Synthetic provisioning | `shop-observability.tf`: source bucket/object, function image repository, two dedicated SAs/scoped grants, function/invoker bindings, monitoring service identity, private email channel and disabled frontend-error policy | Reviewed ZIP/hash and full plan, function ACTIVE/build SUCCESS, private invoker and scoped identities; no scheduled checks yet |
| Scheduled monitoring | Two checks and two check-failure policies; enable frontend-error policy | Separate full plan with scheduling enabled, successful scheduled HTTPS/synthetic runs, at most3GET per synthetic run, trace/log linkage, exact session evidence and notification delivery |
| Incident exercise | Existing dev cartservice only; independent recovery owner/session | Pre-reviewed guarded1-to0 failure, recovery starts by4minutes and completes within8, failed execution/incident/email, recovery run and incident closure, exact cleanup/sample preservation |

Sample-service is a separate workload. Its absence is not repaired by an Online Shop
rollout. Reuse valid sample artifacts after fresh verification; never treat candidate JSON
as an image or an old URI's signature as authorization for another registry.

## Preconditions before a saved infrastructure plan

The isolated generator composes optional endpoint and observability sources into the
existing foundation root and backend. Its private `foundation-features.private.json`
selection has exactly `version: 1`, `endpoint: boolean`, and `observability: boolean`;
omitting the file keeps both compositions disabled. Observability composition requires
endpoint composition because the synthetic monitor consumes its hostname. The generated
feature-selection record participates in the freshness manifest. Canonical sources,
provider locks and cloud/Kubernetes separation remain unchanged. Narrow generated-root
overrides subtract APIs already owned by the core service set; an enabled API is not
necessarily Terraform-managed. There is one state owner per API and resource.

Review composition changes before planning. The generator refuses unexpected files,
including obsolete optional generated files: archive a reviewed root privately, verify
its manifest and remove only identified generated files before reducing composition.
Never copy inputs, backend metadata, provider caches or state into execution roots.
Run generation, freshness and execution guards in the same isolated process before a
full plan. Preserve the exact composition, source/input hashes and locks with its saved
plan; regenerate and recheck them before a separately authorized apply.

The deployment-only decision is in
[`deployment-policy.json`](../deploy/online-shop/deployment-policy.json). Its closed
versioned schema binds the exact project and environment binding. `endpoint_enabled`
is an exact boolean: false renders 39 resources and true renders 45. The file must match
the reviewed deployment revision; it is not read from an older producing revision.
The original environments binding remains immutable producer evidence, including its
legacy endpoint field. Changing deployment policy does not change candidate identity,
images, signing policy or supporting artifacts. Shared producing trust-file mismatches
still block reuse.

A new deployment implementation requires a reviewed deployment revision and new protected
render/release before rollout. An independent validator cannot reinterpret an old live
deployment using changed shared deployment code: retain its compatible reviewed validator
for readback until the new deployment is authorized. Do not relabel the producing or
actual deployment revision to make a gate pass.

For endpoint bootstrap use `shop_edge_enforce_evaluated_rules=false`; preserve the
reviewed hostname and global Gateway architecture. Do not reuse assigned IPs, nameservers,
certificate state or enforcement observations from another execution. Subsequent plans
must retain the explicitly reviewed enforcement input once enabled. Current endpoint
preflight evaluates preview bootstrap; enforcement-mode deployment needs reviewed handling,
not a false snapshot claiming preview.

Provision monitoring with `shop_observability_enabled=true` and
`shop_observability_schedule_enabled=false`; package source using the canonical
`package-source.py` and supply its absolute ZIP path/hash and operator email privately.
The provisioning set has twenty logical resources before existing-resource/import review;
a full plan determines actual adds/imports and enabled APIs. Schedule activation adds two
checks/two alert policies and enables the existing application policy. Do not infer those
counts from a previous plan or silently accept dashboard normalization/layout changes.
Scheduled synthetic monitoring is application monitoring, not automatic infrastructure
shutdown/startup scheduling. No lifecycle schedules or budget alerts are included.

Restoring the previously accepted operational point means protected HTTPS, usable
dashboards and successful scheduled checks with a verified notification channel.
The controlled cartservice failure was not previously accepted: it remains continuation
of #115 after restoration, not a historical success to copy into new evidence.

## Acceptance and milestone boundary

Use [endpoint](../deploy/online-shop/endpoint-README.md),
[dashboard](../monitoring/dashboards/online-shop-dev/README.md),
[synthetic](../monitoring/online-shop/README.md) and
[incident](../monitoring/online-shop/incident-runbook.md) contracts. Any API enablement,
new scoped IAM grants, provisioning, DNS cutover, sample build/signing, rollout, schedule
activation or failure exercise remains a separately authorized cloud change.

Metric descriptor creation can race across exporters. Record actual errors/dropped-items
and observe convergence; eventual successful signals do not prove lossless export. Review
recurrence before making stronger reliability claims. Redis/Collector storage remains
non-durable. Existing artifacts and holds are retained; expired render protection blocks
a future rollout until the normal protection gate is freshly satisfied.

Only after endpoint, sample health, dashboard and #115 incident acceptance have current
linked evidence should milestone8 proceed to documentation/release review for v0.2.0.
Governance/hardening in milestone9 and canary/progression/rollback/load in milestone10
remain subsequent work; no roadmap scenario or release is executed by this document.
