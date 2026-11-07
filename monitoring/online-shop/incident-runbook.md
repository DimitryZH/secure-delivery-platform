# Cart dependency failure and recovery

This runbook is for one separately authorized #115 exercise on `catalog-dev -> dev`. The accepted endpoint is `https://shop.runtimeplatforms.dev`. The current observed cartservice Deployment has one Ready replica, a ClusterIP service on port 7070 and no HPA. Frontend uses `cartservice:7070`. Readbacks must be fresh before execution.

## Effect and time bound

Temporarily scale only `dev/Deployment/cartservice` from one replica to zero. Frontend catalog/cart handlers depend on GetCart and should return HTTP 500 when it is unavailable. The scheduled browse journey should fail at its catalog step, opening the synthetic failure incident. An observed non-health frontend error should also open the warning policy after its 60-second retest. Frontend's `/_healthz` can remain HTTP 200, so the HTTPS check is expected to stay healthy. Confirm the actual condition rather than expecting every policy to fire.

This interrupts dev cart browsing for all visitors. Use an agreed dev window and retain the original template, UID and replica count privately. Start immediately before a known scheduled run, with its next run due within 60 seconds. Restore immediately after the expected incident and operator notification are recorded. Start restoration by five minutes, reserving API and readiness time within the eight-minute exercise bound. Never extend the outage to obtain a notification.

Before starting, have a second operator/session able to run the same guarded recovery commands if the main shell disconnects. Without that recovery owner, defer the exercise. This covers failures outside a PowerShell `finally` block, such as host termination.

Stop and recover immediately on any of these observations.

- The expected synthetic condition/notification is not observed within the five-minute mutation window.
- Either node becomes NotReady, or sample-service in dev/stage/prod loses Ready/Available or HTTP 200.
- Another rollout, HPA, workload-template change or concurrent replica mutation appears.
- Unexpected admission, resource-pressure, monitoring-authentication or Cloud Armor denial prevents attribution to the cart dependency.
- The operator requests recovery.

## Preparation and scoped commands

These commands are for later execution. Supply an existing authenticated kubeconfig and retain all output privately. Explicitly verify project `sre-platform-staging-507220`, context, namespace, active accepted release and app digests first. Compare the fresh protected-release references and holds with #111 evidence. Confirm nodes and sample-service health, no active rollout, both scheduled checks passing, correct email channel, successful delivery and current incident state. Confirm the query/check IDs from Terraform output and readback.

Capture before/after deployments and health responses for sample-service dev/stage/prod. Baseline and final smoke requests are read-only. Resolve any live drift before exercise authorization.

```powershell
$context = 'gke_sre-platform-staging-507220_us-central1-a_secure-delivery-platform'
$privateDir = '.local-validation/issue115-failure'
New-Item -ItemType Directory -Force $privateDir | Out-Null
$raw = kubectl --context=$context -n dev get deployment/cartservice -o json --request-timeout=10s
if ($LASTEXITCODE -ne 0) { throw 'Cannot read cartservice' }
$raw | Set-Content "$privateDir/cart-before.private.json"
$baseline = $raw | ConvertFrom-Json
if ($baseline.spec.replicas -ne 1 -or $baseline.status.readyReplicas -ne 1) {
    throw 'Expected one Ready cartservice replica'
}
$uid = $baseline.metadata.uid
$template = $baseline.spec.template | ConvertTo-Json -Depth 100 -Compress
$rv = $baseline.metadata.resourceVersion
kubectl --context=$context -n dev get hpa -o json --request-timeout=10s
# Stop unless the reviewed readback confirms no HPA targets cartservice.
```

The mutation uses both replica and resourceVersion preconditions. Keep the observation loop in the same shell so `finally` owns recovery. In a second session, record incidents/email and create `recover-now` in the private directory as soon as the failure evidence is sufficient.

```powershell
try {
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(5)
    kubectl --context=$context -n dev scale deployment/cartservice --replicas=0 --current-replicas=1 --resource-version=$rv --request-timeout=10s
    if ($LASTEXITCODE -ne 0) { throw 'Guarded failure injection failed' }

    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (Test-Path "$privateDir/recover-now") { break }
        # Perform fresh node, sample-service and rollout stop-condition checks
        # in the observing session. Create recover-now on any stop condition.
        Start-Sleep -Seconds 5
    }
}
finally {
    $raw = kubectl --context=$context -n dev get deployment/cartservice -o json --request-timeout=10s
    if ($LASTEXITCODE -ne 0) { throw 'Recovery readback failed; recovery owner must act' }
    $current = $raw | ConvertFrom-Json
    if ($current.metadata.uid -ne $uid -or
        ($current.spec.template | ConvertTo-Json -Depth 100 -Compress) -ne $template) {
        throw 'Concurrent replacement/template change; recovery owner must assess'
    }
    if ($current.spec.replicas -eq 0) {
        $currentVersion = $current.metadata.resourceVersion
        kubectl --context=$context -n dev scale deployment/cartservice --replicas=1 --current-replicas=0 --resource-version=$currentVersion --request-timeout=10s
        if ($LASTEXITCODE -ne 0) { throw 'Recovery scale failed; recovery owner must act' }
    }
    elseif ($current.spec.replicas -ne 1) {
        throw 'Unexpected replica count; recovery owner must assess'
    }
    kubectl --context=$context -n dev rollout status deployment/cartservice --timeout=120s --request-timeout=130s
    if ($LASTEXITCODE -ne 0) { throw 'Cartservice readiness not recovered within bound' }
}
```

For recovery from another session, load the private baseline, set `$uid` and `$template` from it, and execute the `finally` commands. Compare UID/template before scaling. An already-restored one-replica Deployment proceeds to readiness verification. Never delete a Deployment, change image/security policy or apply a different release as a response to this exercise.

## Detection and diagnosis

Record UTC for baseline success, scale0, failed execution, incident opening, email receipt, scale1, Ready, successful scheduled execution and incident closure. Keep notification content private and publish only delivery/result timestamps.

- In Cloud Monitoring, filter by the exact synthetic check ID and `cloud_run_revision`. Capture failed step and error, execution ID and native function trace/log links. Distinguish a failed execution from absence of scheduled results.
- In the [#111 dashboard](../dashboards/online-shop-dev/README.md), inspect frontend request/error/success panels and cart desired/available replicas for the same dev window. The deliberate desired=0 must not be interpreted as healthy service.
- Use frontend completion logs, native `trace`/`spanId` and the synthetic application's trace ID. Expect cart client RPC unavailability in the frontend trace and a failed frontend operation. Because cart has zero Pods, cart server spans might be absent.
- In Cloud Armor, verify the synthetic GET reached the frontend and was allowed. WAF/rate/auth failures are a different cause and trigger recovery/diagnosis.
- The application alert retains version/release labels. The synthetic alert identifies the check/function. Join to the current release using independently recorded runtime identity.

## Recovery acceptance

Require one Ready/Available cart replica with the original template/digests and healthy endpoint browsing. Wait for the next scheduled browse run to pass, its state/cleanup evidence, and recovery notifications. The five-minute application rate window can delay the warning's closure after service recovery. Capture that behavior without extending the outage.

Confirm incident closure from actual successful results and the absence of new errors in the following window. Missing samples or an automatically closed incident do not establish recovery. Finally verify sample-service Ready/Available and HTTP 200 in dev/stage/prod, nodes Ready, original app digests, no unexpected rollout, and no owned port-forward remaining. Leave the issue open until review of the sanitized timeline.
