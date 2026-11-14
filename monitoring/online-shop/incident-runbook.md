# Cart dependency failure and recovery

This runbook is for one separately authorized #115 exercise on `catalog-dev -> dev`. The accepted endpoint is `https://shop.runtimeplatforms.dev`. The current observed cartservice Deployment has one Ready replica, a ClusterIP service on port 7070 and no HPA. Frontend uses `cartservice:7070`. Readbacks must be fresh before execution.

## Effect and time bound

Temporarily scale only `dev/Deployment/cartservice` from one replica to zero. Frontend catalog/cart handlers depend on GetCart and should return HTTP 500 when it is unavailable. The scheduled browse journey should fail at its catalog step, opening the synthetic failure incident. An observed non-health frontend error should also open the warning policy after its 60-second retest. Frontend's `/_healthz` can remain HTTP 200, so the HTTPS check is expected to stay healthy. Confirm the actual condition rather than expecting every policy to fire.

This interrupts dev cart browsing for all visitors. Use an agreed dev window and retain the original template, UID and replica count privately. Start immediately before a known scheduled run, with its next run due within 60 seconds. Restore immediately after the expected incident and operator notification are recorded. Start restoration by four minutes, reserving API and readiness time within the eight-minute exercise bound. Never extend the outage to obtain a notification.

Before starting, require the full Online Shop baseline: all application components, Redis and Collector Ready/Available at their reviewed replica counts, original accepted digests, healthy endpoint browsing, and both scheduled checks passing. Require both nodes Ready. If workers are paused, defer the exercise; this procedure does not authorize resume. Have a second operator/session able to run the same guarded recovery commands if the main shell disconnects. Without that recovery owner, defer the exercise. This covers failures outside a PowerShell `finally` block, such as host termination.

During the bounded injection, expected degradation is limited to cartservice desired replicas zero and no available cart Pods, cart RPC unavailability, dependent frontend catalog/cart HTTP 500 responses, and the resulting scheduled browse failure and attributed frontend-error incident. These observations are the intended test signals, not immediate stop conditions. They must correlate to this exact injection window and cart dependency. Missing cart server spans are expected with zero cart Pods. Other application components, Redis, Collector and nodes must retain their baseline readiness and digests; the frontend `/_healthz` and HTTPS check should remain healthy. An error without evidence linking it to the injected cart failure is not an expected result.

Stop and recover immediately on any of these observations.

- The expected synthetic condition/notification is not observed within the four-minute mutation window.
- Either node becomes NotReady, any non-cart workload (including Redis or Collector) loses baseline Ready/Available state, or frontend `/_healthz` / the HTTPS check fails.
- An unrelated endpoint or dependency fails, digests change, or failures cannot be attributed to the injected cart dependency. Do not treat expected cart-dependent HTTP 500 or the browse synthetic failure as collateral failure.
- Another rollout, HPA, workload-template change or concurrent replica mutation appears.
- Unexpected admission, resource-pressure, monitoring-authentication or Cloud Armor denial prevents attribution to the cart dependency.
- The operator requests recovery.

## Preparation and scoped commands

These commands are for later execution. Supply an existing authenticated kubeconfig and retain all output privately. Resolve the project, cluster, location and identities from the current reviewed `deploy/release-binding.json`, cross-check `deploy/environments.json`, then verify the actual project number and selected context's cluster endpoint before any runtime read or mutation. Do not use project identifiers from historical evidence. Confirm namespace, active accepted release and app digests. Compare fresh protected-release references and holds with the current accepted release; #111 is historical guidance only. Confirm the full pre-exercise baseline above, no active rollout, correct email channel, successful delivery and current incident state. Confirm the query/check IDs from current Terraform output and readback.

Capture before/after deployments and health responses for Online Shop. Baseline and final smoke requests are read-only. Resolve any live drift before exercise authorization.

```powershell
$context = '<reviewed-current-context>'  # Explicit isolated context verified against the active binding
$binding = Get-Content -LiteralPath 'deploy/release-binding.json' -Raw | ConvertFrom-Json
$environment = Get-Content -LiteralPath 'deploy/environments.json' -Raw | ConvertFrom-Json
if ($binding.version -ne 1 -or [string]::IsNullOrWhiteSpace($binding.project) -or
    [string]::IsNullOrWhiteSpace($binding.cluster) -or [string]::IsNullOrWhiteSpace($binding.location) -or
    $environment.release_binding -ne $binding.id -or $environment.project -ne $binding.project -or
    $environment.project_number -ne $binding.project_number -or
    $environment.cluster -ne $binding.cluster -or $environment.location -ne $binding.location -or
    $environment.approved_registry -ne $binding.registry -or
    $environment.deployment_service_account -ne $binding.deployer -or
    $environment.environments.dev.namespace -ne 'dev') {
    throw 'Current reviewed environment binding mismatch'
}
$projectNumber = gcloud projects describe $binding.project --format='value(projectNumber)'
if ($LASTEXITCODE -ne 0 -or [string]$projectNumber -ne [string]$binding.project_number) {
    throw 'Actual project does not match the current binding'
}
$clusterRaw = gcloud container clusters describe $binding.cluster --project=$($binding.project) --location=$($binding.location) --format=json
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify bound cluster' }
$cluster = $clusterRaw | ConvertFrom-Json
$contextRaw = kubectl config view --context=$context --minify -o json
if ($LASTEXITCODE -ne 0) { throw 'Cannot verify selected context' }
$contextConfig = $contextRaw | ConvertFrom-Json
if ($cluster.name -ne $binding.cluster -or [string]::IsNullOrWhiteSpace($cluster.endpoint) -or
    @($contextConfig.clusters).Count -ne 1 -or
    $contextConfig.clusters[0].cluster.server -ne "https://$($cluster.endpoint)" -or
    $contextConfig.clusters[0].cluster.'insecure-skip-tls-verify' -eq $true) {
    throw 'Selected context does not match the bound cluster endpoint and TLS requirement'
}
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
    $deadline = [DateTimeOffset]::UtcNow.AddMinutes(4)
    kubectl --context=$context -n dev scale deployment/cartservice --replicas=0 --current-replicas=1 --resource-version=$rv --request-timeout=10s
    if ($LASTEXITCODE -ne 0) { throw 'Guarded failure injection failed' }

    while ([DateTimeOffset]::UtcNow -lt $deadline) {
        if (Test-Path "$privateDir/recover-now") { break }
        # Check nodes, non-cart readiness/digests, independent frontend health,
        # cart-failure attribution and rollout stop conditions. Expected cart
        # unavailability / dependent HTTP 500 / browse failure are test signals.
        # in the observing session. Create recover-now on any stop condition.
        Start-Sleep -Seconds 5
    }
}
finally {
    $recovered = $false
    for ($attempt = 1; $attempt -le 3; $attempt++) {
        $raw = kubectl --context=$context -n dev get deployment/cartservice -o json --request-timeout=5s
        if ($LASTEXITCODE -ne 0) { throw 'Recovery readback failed; recovery owner must act' }
        $current = $raw | ConvertFrom-Json
        if ($current.metadata.uid -ne $uid -or
            ($current.spec.template | ConvertTo-Json -Depth 100 -Compress) -ne $template) {
            throw 'Concurrent replacement/template change; recovery owner must assess'
        }
        if ($current.spec.replicas -eq 1) { $recovered = $true; break }
        if ($current.spec.replicas -ne 0) { throw 'Unexpected replicas; recovery owner must assess' }
        $currentVersion = $current.metadata.resourceVersion
        $errorFile = "$privateDir/recovery-scale-$attempt.private.txt"
        kubectl --context=$context -n dev scale deployment/cartservice --replicas=1 --current-replicas=0 --resource-version=$currentVersion --request-timeout=5s 2> $errorFile
        if ($LASTEXITCODE -eq 0) { $recovered = $true; break }
        if ((Get-Content $errorFile -Raw) -notmatch '(?i)conflict|object has been modified') {
            throw 'Uncertain scale result; recovery owner must read actual state'
        }
        # Only an explicit conflict permits another guarded attempt.
    }
    if (-not $recovered) { throw 'Three recovery conflicts; recovery owner must act immediately' }
    kubectl --context=$context -n dev rollout status deployment/cartservice --timeout=120s --request-timeout=120s
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

Require the full Online Shop baseline again: one Ready/Available cart replica with the original template/digests, every other application component, Redis and Collector at baseline readiness/digests, both nodes Ready, and healthy endpoint browsing including the previously failing cart-dependent paths. Wait for both scheduled checks to pass, the browse run's state/cleanup evidence, and incident closure. The five-minute application rate window can delay the warning's closure after service recovery. Capture that behavior without extending the outage.

Confirm incident closure from actual successful results and the absence of new errors in the following window. Missing samples or an automatically closed incident do not establish recovery. Finally verify Online Shop Ready/Available and expected HTTP health, nodes Ready, original app digests, no unexpected rollout, and no owned port-forward remaining. Leave the issue open until review of the sanitized timeline.

Recovery reserves four minutes after the mutation window. Three attempts each bound GET and scale to five seconds, followed by readiness up to 120 seconds. Conflicts trigger fresh UID/template/replica checks. All other errors and exhausted conflicts transfer immediately to the recovery owner. The pinned Google 5.45.2 provider has no notification_prompts field. Recovery acceptance requires successful scheduled results and observed incident closure; a recovery email is recorded if delivered but is not required.
