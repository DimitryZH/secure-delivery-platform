# Environment-aware deployment

Related to #52. Deployment is a separate operation after verification and
attestation, using `deploy/deploy-release.py`. It does not build, retag, sign,
create namespaces, change policy, or introduce Cloud Deploy.

## Executable boundary

`deploy/environments.json` pins the project, cluster, approved repository,
source/build producer, and separate deployment service identity. All three
environments require a complete release record, `verification_status=passed`,
a UTC verification timestamp, same-project occurrence reference, and the exact
`sample-service@sha256:<digest>` image. Tags and contradictory digests are rejected.

| Target | Namespace / APP_ENV | Additional gate |
| --- | --- | --- |
| dev | dev | Initial explicit deployment |
| stage | stage | Explicit operator review (`--reviewed`) |
| prod | prod | Explicit operator review (`--reviewed`) |

`target_environment` must match the command target. Stage/prod review is an
operator assertion, not an authenticated approval service or automatic
promotion. Before review, the operator checks the previous environment's
runtime result and the same release digest. This CLI does not automatically
validate a dev-to-stage-to-prod history or authorize the next environment.
The differentiated promotion goals in the architecture docs remain manual.

The initial metadata fields are revalidated using the existing verifier.
Verification status and occurrence reference in an input record are declarations,
not cryptographic proof. GKE's existing Binary Authorization attestor requirement
is the authoritative signature gate. The CLI checks cluster enforcement is
enabled; the exact attestor policy remains managed by the existing Terraform.
No arbitrary namespace, image, authority, kubeconfig, or break-glass override is
accepted by this command.

## Authority and current read-only findings

On October 2, 2026, dev/stage/prod existed and there were no application
Deployments, Services, or Pods in them. The earlier temporary validation Pods
were already removed. Deployment identity
`secure-delivery-deploy@sre-platform-staging-***.iam.gserviceaccount.com`
has `roles/container.developer` and `roles/logging.logWriter`. Node image pull
uses the separately provisioned repository reader binding.

Build identity has Artifact Registry writer, Cloud Build builder, and log-writer
grants. Read-only project and deploy-service-account IAM inspection found no
direct build grant for deployment or deploy impersonation. The deploy account's
own IAM policy has no direct bindings. This is not a full organization/group or
deny-policy audit. Existing container.developer permissions are broader than
this CLI's namespace scope; the CLI does not replace IAM/RBAC isolation.

Every execution-side gcloud command explicitly impersonates the deploy account.
kubectl uses that short-lived token, the target cluster endpoint and CA, and an
isolated temporary kubeconfig created as a valid empty Config before use; it
never falls back to the operator's current kubeconfig. The temporary kubeconfig
and CA are removed on success or failure; the token is not stored in that Config.
Tokens are not written into release results. The reviewed operator
must already be allowed to impersonate that account (normally Token Creator).
No new impersonation grant or build-side delegation is added. A build identity
without that permission fails to obtain the deployment token before apply.
Live impersonation/RBAC access was not exercised by this preparation.

## Prepare and execute

Requirements for execution: Python 3.10+, gcloud and kubectl, reviewed operator
authentication, deployed foundation/enforced attestor policy, node repository
reader access, and a current attestation. Preparation only needs Python.

The CLI resolves executables through PATH, including `gcloud.CMD` on Windows,
and passes arguments without a shell. Linux/macOS use their PATH executables.
No local launcher or manually pre-created kubeconfig is required.

`deploy/examples/verified-release.json` contains synthetic build/digest/occurrence
values targeted to dev with placeholders for project and service-account metadata.
It is an offline preparation example, not a real verified or deployable candidate.
Replace it with a privately retained real verification/attestation record before
execution. Never copy the example's claimed passed status into a live candidate.
Materialize the synthetic example locally from the executable configuration
(the generated record stays ignored), then prepare without any cloud commands:

```python
import json
from pathlib import Path
policy = json.loads(Path("deploy/environments.json").read_text())
example = Path("deploy/examples/verified-release.json").read_text()
for key, value in {"project_id": policy["project"],
                   "approved_registry": policy["approved_registry"],
                   "build_service_account": policy["build_service_account"]}.items():
    example = example.replace("${" + key + "}", value)
output = Path("docs/private/issue52/example.json")
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(example)
```

```sh
python -B deploy/deploy-release.py --metadata docs/private/issue52/example.json --environment dev --output-dir docs/private/issue52/dev
```

For each other target, copy the same record and change only
`target_environment` to `stage` or `prod`; preserve all release identity fields.
Use `--reviewed` for preparation too. For example, with a reviewed stage record:

```sh
python -B deploy/deploy-release.py --metadata release-stage.json --environment stage --reviewed --output-dir docs/private/issue52/stage
```

After separate deployment authorization, append `--execute` to the relevant
command. It applies a namespaced Deployment and ClusterIP Service, waits up to
120 seconds for rollout, confirms the current generation's available replica
and exact template digest, and emits `deployment_status=deployed`, UID and time.
Both workload and Pod template preserve commit, build, digest, verification,
trust reference, environment, and deployment-authority correlation through
the deployment result and template annotations. `release_name` is not fabricated
because no Cloud Deploy release exists.

Failure exits nonzero and emits a failed result without `deployed_at`. Errors
exclude token-bearing commands and subprocess stderr. A failed rollout can
leave the Deployment/Service configured; there is no automatic destructive
rollback or cleanup of an existing application. An unsigned Deployment object
may be accepted while its Pod creations are denied by Binary Authorization:
rollout success, not apply exit alone, is required. Operators inspect the target
ReplicaSet events to distinguish admission denial from scheduling/image-pull
failures. Re-execution applies the same reviewed candidate; it never rebuilds.

## Validation preparation and pending live checks

```sh
python -B -m unittest discover -s scripts/tests -p 'test_*py' -v
```

25 offline tests passed, including ten focused deployment test methods and
their subcases. They exercise preparation for every environment, release
identity preservation, invalid/tagged/foreign/mismatched candidates, missing
trust reference, failed verification, review/target guards, duplicate JSON,
separate authority, and simulated impersonation, disabled enforcement,
admission/rollout failure and runtime digest mismatch. Portability regressions
cover Windows/Linux/macOS executable resolution, sanitized missing-command
and subprocess failures, and temporary kubeconfig creation/cleanup. Cloud commands are
stubbed; this proves executable control flow, not live GKE deployment authority.

After authorization, positive validation should execute the existing attested
sample digest through the deploy identity in dev, inspect its Pod imageID,
Running/Ready, HTTP health and release annotations, and save the result/events.
Negative local cases must fail without cloud calls. For live policy validation,
use the real unattested sample digest from Issue #49 with a test-only record
whose claimed passed status/reference cannot establish cryptographic trust;
the GKE attestor gate must reject Pod creation and rollout must fail. Save
ReplicaSet events and confirm no candidate container ran. Do not use break-glass.
Clean up only separately authorized test-created resources, preserving prior
workloads. Direct build impersonation-denial validation is also pending.

No Terraform apply, deployment, API/IAM/policy change, artifact rebuild/retag,
live signing, or GCP resource mutation was performed for this preparation.
