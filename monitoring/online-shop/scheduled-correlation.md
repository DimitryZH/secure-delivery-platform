# Recorded synthetic and edge correlation

The recorded execution `bfe368073e0ea55ab311d6afb9615cea` passes the [offline diagnostic](diagnose-scheduled.py). It validates existing evidence only: no Cloud API, checkout, function invocation, Redis command or schedule mutation. This establishes scheduled browse acceptance for that historical run, not current application health or completion of the controlled failure exercise.

## Why LB trace identity is separate

The rejected `armor_trace_mismatch` assertion came from an operator-local diagnostic script. It required every edge log's native `trace` field to equal the function/application native trace. Neither the synthetic SDK contract nor the reviewed application checks established that LB equality requirement.

The deployed source ZIP `a84b3c430f8be229057d88ebac1e3b1fb2f15146def6d9feca43eb9590b3ffb4` activates a function span, extracts W3C context and injects it into outbound HTTPS. `OTEL_PROPAGATORS=tracecontext` disables baggage. The source doesn't explicitly send `X-Cloud-Trace-Context`. Saved spans show the function's three HTTPS client spans and direct frontend SERVER children under the **same trace ID**. Native function and 111 application log records link to the corresponding exported spans. That is positive evidence of uninterrupted application W3C propagation.

Read-only inspection confirmed the global external Application Load Balancer, `EXTERNAL_MANAGED`, public IP `8.233.86.84`, frontend backend and logging sample rate 1. Google documents that this LB adds legacy [`X-Cloud-Trace-Context` when absent](https://docs.cloud.google.com/load-balancing/docs/https#target-proxies). The distinct edge IDs are consistent with separately generated legacy context. Raw wire headers were not retained, so the exact header transformation cannot be proven from these snapshots.

The newer [distributed tracing feature](https://docs.cloud.google.com/load-balancing/docs/distributed-tracing-overview) uses a Network Services `TelemetryPolicy` targeting forwarding rules. Terraform in this repository doesn't configure one. The current Network Services API is DISABLED and its global telemetry-policy list returns `403 / SERVICE_DISABLED`. Therefore live absence of policies is **not confirmed**; no API or permission was enabled for this investigation. A current inventory limitation also cannot prove historical absence at execution time. We don't infer a common LB/application identity from either condition.

The corrected diagnostic retains LB native IDs as separate evidence and reports whether they match. A difference alone doesn't fail the application trace check. Function trace ID, exported function span, client/parent/frontend relationships, native app trace/span IDs, release identity, component digests and version/dev attribution remain mandatory. The accepted complete candidate is checked with the existing local policy reconstruction and an explicitly supplied reviewed release-set ID. This offline procedure does not repeat cloud provenance/signature verification or authorize any deployment.

## One-to-one operational edge matching

All times below are UTC on 2026-11-08. Each edge request, including its recorded latency, fits entirely inside exactly one non-overlapping HTTPS client-span interval in the execution's common W3C trace. No clock-skew allowance is needed for this recorded join.

| Method and path | HTTPS client interval | Edge start | Result |
| --- | --- | --- | --- |
| GET `/` | 15:09:19.888–15:09:20.309081524 | 15:09:19.967548 | 200 / ACCEPT |
| GET `/product/OLJCESPC7Z` | 15:09:20.311–15:09:20.368025994 | 15:09:20.313783 | 200 / ACCEPT |
| GET `/cart` | 15:09:20.370–15:09:20.411008267 | 15:09:20.370640 | 200 / ACCEPT |

The match also requires all of the following:

- Exact HTTPS hostname/URL and GET method from the exported client span; the frontend child must have the corresponding route and HTTP 200.
- `sdp-online-shop-synthetic/browse-v1` User-Agent. The source also sends `X-SDP-Synthetic: browse-v1`, but that header and the session cookie are not present in the retained LB records and are not asserted as observed.
- The same private source IPv4 across all requests, equal to the Armor IP key. This IP is recorded by the edge; independent function-egress/NAT proof isn't available.
- The reviewed project, global forwarding rule, HTTPS proxy, URL map and frontend backend. Edge `serverIp` matches the independently read Ready frontend Pod; its name also matches application span instance attribution.
- Policy `shop-dev-edge`, priority 2000, THROTTLE/ACCEPT and `RATE_LIMIT_THRESHOLD_CONFORM` for all three requests.
- A complete, unsampled candidate capture: sample rate 1, all Logging API continuation pages exhausted, and exactly one edge candidate per request. Empty continuation pages must still be followed. Missing/extra/ambiguous candidates fail.

Thus the association is unique **within the complete retained candidate set**. It is an operational evidence join, not cryptographic attribution: execution ID isn't recorded at the edge, the User-Agent is stable rather than unique, and an IP can be shared. If simultaneous matching traffic makes it ambiguous, acceptance blocks rather than selecting the nearest entry. Raw IPs, session material and full snapshots stay private.

## Reproducing the recorded diagnostic

Assemble a private snapshot without changing trace/timestamps/logs/metrics: `version=1`, the accepted `candidate`, recorded `release`, `function_logs`, `trace`, `application_logs`, `edge_logs`, reviewed `edge_context`, `edge_capture` and recorded `session_readback`. Context includes the independently read LB resource names/address and backend Pod IP; source-IP consistency comes from the retained edge records. Capture metadata includes its actual query window, sample rate and exhausted-pagination status. Verify aggregate logs against every retained raw page before declaring the capture complete. Record the builder/readback provenance privately; snapshot inputs aren't authenticated by this local CLI.

```powershell
python monitoring/online-shop/diagnose-scheduled.py --snapshot <private-snapshot.json> --execution-id bfe368073e0ea55ab311d6afb9615cea --monitor-version a84b3c430f8be229057d88ebac1e3b1fb2f15146def6d9feca43eb9590b3ffb4 --release-set-id sha256:d3ddfc09ec0f0195d38fadfba8a2c31ce290b41bf4211ac4631a5b20039d3891
```

Exit 0 reports `recorded_execution_acceptance=passed`, strict native W3C correlation, three unique edge matches, `edge_native_trace_id_matches_application=false`, and the previously recorded exact-session `EXISTS=0`/closed-forward evidence. It issues no fresh Redis read and makes no claim about present-day state. Exit 1 blocks incomplete or inconsistent evidence. Preserve the earlier failed diagnostic as history.

The redeploy produced build `2587f0ad-ea1a-4036-9e58-b4a94e586209` SUCCESS and revision `shop-dev-browse-00002-ril` ACTIVE. Two scheduled successes were observed; the selected run used three GETs in 529 ms. Incident `0.oequ1e89idz7` closed at `2026-11-08T15:12:03Z`. The prior failure email was operator-confirmed. These results satisfy scheduled browse/correlation recovery evidence; the separately authorized cartservice failure, its notification and subsequent recovery remain pending review. The rollback source copy remains under its previously confirmed temporary hold. No source ZIP, runtime, infrastructure, IAM or schedule change is required for this diagnostic correction.
