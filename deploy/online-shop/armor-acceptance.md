# Bounded Armor enforcement acceptance

**Prepared, not executed.** Reuse the trusted Shop release and artifacts. This procedure does
not authorize apply, temporary rules or traffic. The live policy still has WAF/rate preview;
a desired enforcement input and a saved plan do not change that fact.

## Read-only findings and apply gate

The active frontend backend references `shop-dev-edge` with logging sample rate 1. Rules are:
100 `deny(403)` probe; 1000 sensitivity-1 SQLi/XSS `deny(403)` in preview; 2000 IP throttle
1200 requests/60s with `deny(429)` in preview; default 2147483647 ALLOW. Priority 1500 is free.
Existing sampled rate-preview logs show ACCEPT. The bounded capture reached its page cap,
so it is **not** an exhaustive verdict count. The complete 24-hour query found no priority 1000
preview matches. Normal/scheduled acceptance is not SQLi/XSS denial evidence.

A fresh full foundation plan contains only one Armor update and its related operator output:
preview true->false on1000/2000. Provider5.45.2 also clears an unused throttle
`ban_duration_sec` from0 to null; it does not introduce banning or change1200/60/IP.
Google limits [banDurationSec](https://docs.cloud.google.com/compute/docs/reference/rest/v1/securityPolicies/insert)
to `rate_based_ban`. No workload, IAM, capacity or other resource action is included.
Computed cluster embedded pool counts reflect the completed resume, not planned pool changes.
Keep the reviewed `shop_edge_enforce_evaluated_rules=true` private input for subsequent plans;
mark it **pending apply** while live rules remain preview. A capacity-only plan must block if
it unexpectedly includes this enforcement update. Never apply it under pause/resume authority.

**Before apply:** review active-environment WAF preview evidence and false-positive risk.
If the two selected inert SQLi/XSS probes have no existing suitable proof, request their
bounded preview execution first. Do not create traffic now or substitute historical evidence
from another environment. Recheck saved-plan inputs/state/hash and unchanged scope; apply
needs separate authorization. Wait for the policy operation and actual1000/2000 `preview=false`.
A normal GET and backend health must pass before denial tests. Do not weaken WAF or add bypasses.

## Explicit validator modes and revision boundaries

Endpoint-on `complete.py preflight` requires `--armor-mode preview|enforcement`, selected from
reviewed Terraform inputs, never from logs/rule flags. Preview requires the original
`target.armor_preview_policy_ready`; enforcement requires
`target.armor_enforcement_policy_ready`. Do not supply both. Actual raw WAF/rate rule modes,
actions, matches and1200/60/IP must agree; all source/signature/inventory/admission/capacity/
Gateway dry-run/protection guards remain required. Temporary1500 blocks the exact four-rule
preflight until cleanup; do not omit it from evidence.

`diagnose-scheduled.py` already supports the explicit same modes. Rendering and the trusted
candidate are unchanged by mode selection. This PR changes a reviewed deployment executable:
run its live path only after merge. Do not claim an old protected release has the new
source SHA or bypass trust-file matching. For current workload readback, retain a compatible
reviewed validator; a future deployment uses its own reviewed SHA/protected release. An Armor
apply alone does not authorize or require a new application rollout.

## Future bounded request budget

No checkout/orders or load test are included. Use reviewed existing checkout evidence for
false-positive review; if insufficient, request a separate bounded journey rather than
silently creating an order. Capture UTC, exact URL/method, unique User-Agent/marker, source IP,
backend/policy, HTTP result and complete request logs. Never use a CLI access token as an HTTP
header to the public application.

| Phase | Maximum application requests | Required evidence |
| --- | --- | --- |
| Preview review, if missing | 3 normal GETs plus one inert SQLi and one inert XSS GET (5 total) | Normal allowed; selected malicious queries match preview1000 with expected deny action; policy unchanged |
| After separately approved enforcement apply | 3 normal GETs plus the same SQLi/XSS GET once each (5 total) | Normal HTTPS chain/hostname valid and200; each malicious GET403 plus enforced1000/DENY and matching configured WAF rule IDs |
| Scoped throttle mechanism | At most15GETs total, including up to12 in one60s series | Actual429 plus enforced1500/DENY/RATE_LIMIT_THRESHOLD_EXCEED; recovery200 and HEALTHY backend |

Each phase is separately authorized or explicitly included in a larger reviewed request.
Use the exact immutable probe definitions in the private execution manifest after preview
review; never improvise alternate payloads/retry to obtain403. Proposed inert query values
are `sdp_probe=1' OR '1'='1' --` and `sdp_probe=<script>alert(1)</script>` on `/_healthz`,
URL-encoded by the client, with no redirects/retries and no application write. Preview must
establish their actual match before relying on them. A200 or wrong rule is NOT_CONFIRMED,
not an excuse to increase traffic or claim a denial. Stop on unexpected5xx/backend or workload
errors, unexpected rule/action, identity mismatch or an operator stop request.

## Scoped throttle test and exact cleanup

1. Read the current **enforced** policy and backend before the test; save its full rule set,
   fingerprint and operation evidence privately. Verify1500 free, no concurrent policy/Terraform
   apply, operator permission and a local exclusive test marker. Abort if another rule occupies1500.
2. The first of the15budgetedGETs identifies the operator's exact public IPv4 from its unique
   edge log. Do not guess it or use synthetic-function/NAT evidence from another request.
3. Prepare one temporary rule: priority 1500, description containing a fresh128-bit marker,
   `throttle`, preview=false, allow conforming traffic, exceed `deny(429)`, IP key, threshold3/60s.
   The CEL match requires **all** of:

   ```text
   inIpRange(origin.ip, '<verified-IPv4>/32') &&
   request.method == 'GET' && request.path == '/_healthz' &&
   has(request.headers['x-sdp-edge-test']) &&
   request.headers['x-sdp-edge-test'] == '<unique-marker>'
   ```

   Use the marker in the User-Agent too, so logs support correlation without claiming a
   normally unlogged request header was observed. Review the complete expression before create.
4. After separate authorization, conditional full-policy PATCH includes the fresh fingerprint
   and current rules plus exactly this rule. Wait for operation success; read back exact scope.
   An ambiguous response/412 requires read-only recovery, never blind recreation.
5. Send at most12markedGETs within60s; stop at first429 or unexpected status. Match429 to
   policy 1500, DENY and RATE_LIMIT_THRESHOLD_EXCEED with the exact IP key and request identity.
   A low threshold is not a guarantee of the fourth response: limits are
   [approximate and backend/region scoped](https://docs.cloud.google.com/armor/docs/rate-limiting-overview).
   Budget exhaustion without429 is NOT_CONFIRMED; no second series is authorized.
6. **Finally, including failure:** read policy; prove1500 still belongs to this exact marker
   and scoped rule. Remove only that rule using the fresh fingerprint and current remaining
   rules, preserving any unrelated change. Never restore an old full snapshot over concurrent
   edits. On412/uncertainty inspect actual state; escalate unresolved cleanup rather than
   deleting a foreign rule. No automatic broad cleanup or Terraform apply during the test.
7. Confirm operation completion,1500 absent, original enforced baseline rules unchanged, no
   other test rule, and exact backend binding. Wait a full60s window after the last marked
   request; use remaining budgeted unmarked healthGETs (maximum2) to confirm200 and HEALTHY
   backend. Record cleanup even when the test did not prove429. Temporary-rule lifetime budget
   is15minutes; unresolved deletion transfers immediately to the operator, not an abandoned rule.

Only an attributed actual429 proves the mechanism. This test does **not** prove the real
priority 2000 threshold1200/60s: retain that result separately as NOT_CONFIRMED unless matching
existing/live evidence proves it. No 1220-request series is included here.

All requests/operations/cleanup remain pending. Review/publication of platform v0.2.0 is tracked
separately in [#133](https://github.com/DimitryZH/secure-delivery-platform/issues/133), not performed here.
