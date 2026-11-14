# Online Shop scheduled checks

For active-environment preparation, follow the [baseline recovery gates](../../docs/platform-baseline-recovery.md).
Historical IDs/results below are not operational defaults or current acceptance.
Use the isolated execution roots and reviewed private inputs; never reuse a cached
historical backend to provision these resources.

The #115 configuration provisions a public HTTPS uptime check, a Cloud Monitoring synthetic monitor and email alerts for the accepted dev Online Shop. The existing [dashboard and native correlation procedure](../dashboards/online-shop-dev/README.md) supplies diagnosis. Read-only results and validation limits are in [validation.json](validation.json). The [incident runbook](incident-runbook.md) defines the separately authorized failure exercise.

## Observations and thresholds

On 2026-11-07 the project had no uptime checks, synthetic monitor configurations or notification channels. The existing sample-service availability policy was enabled with no channels. Cloud Functions API was disabled, so its API returned HTTP 403 and its function inventory could not be inspected. A valid-TLS read-only request to `https://shop.runtimeplatforms.dev/_healthz` returned HTTP 200 and `ok`.

Cloud Armor `shop-dev-edge` enforces priority 100's probe-path denial, SQLi/XSS at 1000, and IP throttle 1200/60 seconds at 2000. Clean scheduled GETs use the existing public HTTPS route and stay under that budget. Monitoring returned 54 public checker IP records. The function's egress uses ordinary public HTTPS. Require real WAF/rate readbacks from both checker traffic and a scheduled function run before approving the exercise.

| Policy | Proposed condition and rationale | Missing observations |
| --- | --- | --- |
| HTTPS | At least two checker locations fail for 120 seconds. Period 60 seconds, request timeout 10 seconds, selected USA/Europe/Asia-Pacific regions. One failed location alone does not open this condition. The current endpoint and #111 acceptance were healthy. | A separate OR condition opens after five minutes without results. |
| Synthetic | One observed failed run. Period five minutes, check timeout 60 seconds. The journey has a 30-second internal deadline. Waiting for two scheduled failures would delay diagnosis of this low-traffic dev environment. | A separate OR condition opens after 15 minutes without results. |
| Frontend errors | Positive rate of completed non-health frontend server requests with non-`ok` outcome over five minutes, evaluated every 30 seconds and retained for 60 seconds. The preceding 24-hour read-only query found no nonzero frontend error series. At low volume, one actual server error deserves operator review. A single error can keep this condition true for its five-minute rate window. | Missing request/error series give an empty vector. Independent check-result absence conditions monitor observability. |

The accepted #111 14-request checkout completed in a few seconds. The request/deadline budgets allow headroom, while deployed cold starts remain unmeasured. These are initial operational thresholds for dev. The [frontend PromQL](frontend-errors.promql.tftpl) preserves service, environment, version and release-set labels and excludes health probes. HTTP responses below 500 are `ok` in the accepted application instrumentation. Cloud Armor rejects and connection failures may never reach the application counter. Synthetic and HTTPS alert filters use `monitoring.googleapis.com/uptime_check/check_passed`, the exact check ID, and respectively `cloud_run_revision` and `uptime_url`. The [official synthetic creation guide](https://docs.cloud.google.com/monitoring/synthetic-monitors/create) documents these filters.

The operator selected email. The address is supplied through private `TF_VAR_shop_operator_email` and remains sensitive in Terraform. The operator confirmed receipt of the scheduled-failure notification for incident `0.oequ1e89idz7`; exact receipt time is not recorded. Alerts link to the runbook.

## Synthetic journey and state

The [Node.js function](synthetic/index.js) uses the official Synthetics SDK, Node.js 22 and a committed npm lockfile. Targeted Axios 1.21.0 and Jaeger propagator 2.12.0 overrides remove the high advisories found in the upstream dependency tree. The final npm audit reports zero high/critical and 50 moderate affected dependency entries. Review the remaining advisories before provisioning; the local SDK context test passed with these overrides. Cloud Monitoring records the execution outcome and latency. These service-owned check metrics have their own ingestion path; the application metrics retain the existing Collector path. The HTTP entry point explicitly activates and ends a server span with the SDK-registered provider, extracting W3C trace context from the invocation. The journey requires a recording span with a valid identity. Outbound HTTPS explicitly injects the active W3C context, including when framework startup loaded HTTP modules before auto-instrumentation. `OTEL_PROPAGATORS=tracecontext` keeps baggage disabled. Logs retain execution ID, step, dev attribution and application trace ID; function version is the reviewed source ZIP SHA-256. Compare actual app version/release/digest from app spans and native logs to the accepted release, using the #111 procedure.

Each execution derives a unique in-memory `issue115-` session cookie.

1. GET `/` and choose the first same-origin product ID from its catalog link.
2. GET `/product/<that-id>` and require the selected product identity.
3. GET `/cart` and require the empty-cart response.

The maximum is three HTTP requests, eight seconds per request, 30 seconds for the journey, 45 seconds for the function and 60 seconds for the check. HTTP 200 is required at each step. Redirects, retries, asset downloads and arbitrary links fail the bounded journey. The function has one maximum instance, concurrency one and zero minimum instances. Each response body is capped at 2 MiB.

The pinned AML revision `89fd1cde8285761cc2a35dfb22d145adb2eed980` has `GetCartAsync` call `_cache.GetAsync(userId)` and return an empty cart for an absent key. The selected GET handlers call GetCart without AddItem/EmptyCart. This journey creates no Redis key or order, including partial failure. Its cookie is discarded in `finally`. Local tests check partial failure and cleanup.

For live acceptance, derive the exact run session with the exported `sessionForExecution(executionId)` function from its actual SDK execution ID. It uses `issue115-` plus the first 32 hex characters of SHA-256 of that ID. Only inspect this owned session key at the scoped Redis endpoint, require `EXISTS=0` after successful and failed runs, and close the operator-owned loopback forward. Keep the derived key private. The production logger records the execution ID but omits cookie and response contents. The successful full checkout and exact Redis cleanup from #111 remain the purchase-flow evidence.

The scheduled path checks catalog/cart browsing and dependencies including currency, cart/Redis and shipping. Payment/email and order confirmation require the separately bounded checkout procedure. SDK and application trace/log records are retained observability evidence. Scheduled traffic contributes to application panels. Filter `sdp-online-shop-synthetic/browse-v1` or `X-SDP-Synthetic: browse-v1` in edge logs, then join native trace/span IDs. Session IDs remain outside metric dimensions.

## Resources, access and plans

[Foundation Terraform](../../terraform/foundation/shop-observability.tf) adds the Cloud Functions API, tracks already-enabled Run/Pub/Sub APIs, a dedicated source bucket and Artifact Registry repository, separate build/runtime accounts, the function and scoped IAM, a Monitoring service identity, an email channel, two checks and three policies.

- Runtime has only Cloud Trace Agent. Cloud Run captures stdout, and Monitoring owns check-result metrics. Private Kubernetes/Redis access is unnecessary.
- Build has Logs Writer and Service Usage Consumer. Artifact Registry Writer is scoped to the new function repository, source Object Viewer to the dedicated source bucket, and managed-source Object Viewer to this function's exact regional prefix. See [custom build account permissions](https://docs.cloud.google.com/functions/docs/building). The provisioner needs actAs on these new accounts. Standard Functions/Cloud Build service-agent roles are deployment prerequisites.
- `google-beta` 5.45.2 is pinned for the Monitoring service-identity resource. The Google-managed Monitoring notification service agent receives Cloud Run Invoker and function metadata Viewer on this function only. The function allows external ingress for authenticated Monitoring invocation. Its runtime account is separate.
- Function execution and dependency installation require public HTTPS egress. There is no new VPC connector, Redis exposure or NAT.

For the provisioning plan, use the existing foundation backend/workspace/private inputs, retain `shop_edge_enforce_evaluated_rules=true`, set `shop_observability_enabled=true` and leave `shop_observability_schedule_enabled=false`. Package source locally first.

```powershell
New-Item -ItemType Directory -Force .local-validation/issue115 | Out-Null
python monitoring/online-shop/synthetic/package-source.py .local-validation/issue115/shop-synthetic.zip
# Supply its absolute path via TF_VAR_shop_synthetic_source_zip.
# Supply TF_VAR_shop_operator_email privately.
terraform -chdir=terraform/foundation plan -var=shop_edge_enforce_evaluated_rules=true -var=shop_observability_enabled=true -out=<private-plan>
```

After separate apply approval, verify authenticated invocation, ZIP generation/hash, account bindings, email channel and build success. Then review a second full plan with `shop_observability_schedule_enabled=true`. That apply creates the checks, starts schedules and enables alerts. A reviewed plan with that flag false removes scheduled checks and their policies and disables the application policy while retaining function/channel. Both flags default false.

At five-minute frequency there are about 8,640 synthetic runs and at most 25,920 storefront GETs per 30 days. At $1.20/1,000 executions, the synthetic service alone is about $10.25 after the 100-run billing-account allotment, or $10.37 if that allotment is used elsewhere. HTTPS checks add regional executions, plus function compute, logs/traces, source/image storage and source-build costs. Zero minimum instances avoids idle function compute. Free allowances and actual runtime determine the total. See [Observability pricing](https://cloud.google.com/products/observability/pricing). Retire exact obsolete source/image versions after checking rollback references.

## Live acceptance after review

1. Review/apply provisioning separately, then verify the authenticated function, private channel. Review/apply schedule enablement separately. Both checks must record success before the exercise.
2. Record a successful scheduled run, three-request maximum, runtime/config hash, exact check IDs and current dev release. Confirm step logs and native app trace links, zero Redis state for the derived exact execution session and closure of the owned forward, including partial failure. Inspect real Cloud Armor verdicts.
3. Confirm delivery to the designated email. Follow the bounded [cart dependency failure](incident-runbook.md) after exercise authorization.
4. Record policy condition, incident ID, detection delay and operator receipt time. Diagnose the affected frontend operation and cart dependency through dashboard, traces and logs.
5. Restore one cartservice replica within the bound. Require application recovery, a subsequent successful scheduled run, incident closure based on success samples.
6. Check sample-service dev/stage/prod and final app health. Publish sanitized timing/results. Raw responses, session correlation and email stay private.

Provisioning and schedule enablement have completed. The HTTPS check passed from five locations. The synthetic check failed before any Shop GET with `synthetic_trace_context_missing`, opened incident `0.oequ1e89idz7`, and delivered the operator-confirmed failure email. The exact derived session key read back `EXISTS=0` and the owned forward was closed. The merged fix subsequently passed scheduled browsing and application correlation, and this incident closed. See [recorded synthetic/edge correlation](scheduled-correlation.md) for the retained evidence, corrected LB identity assumption and data limits. The separately authorized cartservice failure exercise remains pending.

## Dependency advisory review

The 50 moderate affected entries resolve to three unique advisory IDs, rather than 50 independent defects. See [advisories](dependency-review.md). The pinned provider schema lacks notification_prompts, so successful scheduled results and incident closure establish recovery. Recovery-email delivery is optional evidence.

## Scheduled trace-context fix and redeploy review

Read-only inspection confirmed deployed revision `shop-dev-browse-00001-xix`, build `e4b7aa94-09ce-465b-8c5a-e229c369c0da`, and the original source ZIP SHA-256 `11cfa200fdc3a7434230588b0fad5a230ed8e00f214b7e14ac245e5b917fb7b6`. At that investigation snapshot the incident was OPEN and scheduling remained enabled; the subsequent recorded run and closure are described in [scheduled correlation](scheduled-correlation.md). The notification screenshot identifies the expected check/condition and displays the alert start minute (19:55 UTC), not an exact email receipt time.

Functions Framework 5.0.5's CLI imports its server (HTTP/Express) before loading the user module. SDK 0.7.0 registers instrumentation/provider in that user module; its `runSyntheticHandler` awaits its logger and invokes the callback without creating an active span. An incoming Cloud Run trace field does not itself establish OpenTelemetry active context. The original direct SDK fixture supplied a span manually, masking the real startup order. A real framework CLI invocation reproduced the deployed error before the first GET. As a diagnostic control, preloading SDK initialization before that CLI made the old handler pass through real HTTP/TLS without a manually supplied span, isolating the startup-order dependency.

A fresh install of the deployed lockfile resolves API 1.6.0, NodeTracerProvider 1.17.0 and AsyncLocalStorageContextManager 1.17.0. Application, SDK and provider share the same API instance. The new HTTP-entry-point regression validates recording context across async boundaries, root and remote-parent invocation, native log trace/span fields, exactly three real TLS GETs, disabled baggage, and partial-failure cleanup. It also passes with HTTP auto-instrumentation disabled. Only remote trace export and the network destination are replaced: TLS is validated against a test-only certificate on loopback. The test certificate/key under `synthetic/test/` are public fixture material, never deployed. Deployed module-cache state is not exposed by these read-only APIs; dependency compatibility is established by the source lockfile, SDK execution metadata and fresh-install HTTP reproduction, not a live runtime diagnostic injection.

Run local checks from an ignored copy of the source with `npm ci --ignore-scripts` and `npm test`; the HTTP tests need loopback listeners and Node.js 22. The source archive intentionally excludes tests, fixture certificates and node_modules.

After merge, package the **merged** source and review a fresh full foundation plan before any apply:

```powershell
python monitoring/online-shop/synthetic/package-source.py <new-private-absolute-zip-path>
# Verify the printed SHA-256; set private TF_VAR_shop_synthetic_source_zip to that path.
# Keep existing backend, default workspace, private inputs/email, and all three flags true:
terraform -chdir=terraform/foundation plan -var=shop_edge_enforce_evaluated_rules=true -var=shop_observability_enabled=true -var=shop_observability_schedule_enabled=true -out=<private-saved-plan>
```

The new ZIP/hash is recorded in [validation.json](validation.json). Expect a new content-addressed source object and an update of the existing function's pinned source generation and `MONITOR_VERSION` (and any independently reviewed API normalization). Require no changes to IAM, checks/schedules, alert policies, Cloud Armor, workloads or dashboard behavior. Keep the existing source generation available for rollback. Inspect all plan actions and drift; apply is a separate approval. Then verify build/revision/source hash and wait for a scheduled run, without manually generating traffic. Require three GETs, native application correlation, Armor verdicts, exact derived-session `EXISTS=0`, incident recovery and operator evidence before approving the failure exercise. The later approved redeploy completed; its recorded scheduled acceptance is described in [scheduled correlation](scheduled-correlation.md). No controlled failure exercise has been performed.
