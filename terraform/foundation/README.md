# Terraform Foundation

This directory is intended for the shared infrastructure backbone of the platform.

The foundation should create the smallest reproducible Google-native baseline needed to demonstrate trusted delivery. It should not become a generic Terraform framework or an enterprise platform module system.

## Safe local validation

From this directory, copy the example variables file and replace the placeholder project ID with a valid Google Cloud project ID:

```shell
cp terraform.tfvars.example terraform.tfvars
terraform init -backend=false
terraform fmt
terraform validate
```

This procedure validates the local Terraform configuration only. Provisioning is not part of this change.

## Future GCS backend initialization

After an explicitly authorized bootstrap has created the state bucket, copy `backend.hcl.example` to the ignored local `backend.hcl` file and replace the bucket placeholder with the bootstrap `state_bucket_name` output. The prefix is already set to `secure-delivery-platform/foundation`.

An operator may initialize the GCS backend and migrate existing foundation state only after separate explicit authorization:

```shell
terraform init -backend-config=backend.hcl -migrate-state
```

State bucket provisioning and state migration are not part of this change.

## MVP foundation inventory

The first executable foundation should include only the resources required for the trusted release path:

| Area | MVP resources | Purpose |
| --- | --- | --- |
| Service enablement | Required Google Cloud APIs | Enable the platform services used by the baseline |
| Artifact storage | One Artifact Registry Docker repository | Store release candidate images |
| Runtime | One GKE cluster | Run the sample service across MVP environments |
| Environment separation | `dev`, `stage`, and `prod` namespaces | Demonstrate environment progression without multi-cluster complexity |
| Build identity | Cloud Build execution service account | Build, verify, and publish release candidates |
| Deploy identity | Deployment execution service account | Deploy through the controlled release path |
| Review identity | Operator or reviewer IAM bindings | Support release review without broad administrative access |
| Trust enforcement | Binary Authorization prerequisites | Prepare deployment trust enforcement |
| Promotion | Cloud Deploy prerequisites | Prepare explicit environment progression |
| Observability | Minimal logging and monitoring access | Support operator review and release visibility |

## Required APIs

The MVP foundation should enable only the APIs needed by the baseline:
- Cloud Build
- Artifact Registry
- Google Kubernetes Engine
- Binary Authorization
- Cloud Deploy
- Cloud Logging
- Cloud Monitoring
- IAM

Additional APIs should be added only when a documented MVP capability requires them.

## IAM baseline

IAM should reinforce the trusted release model.

Minimum identities:
- build execution identity
- deployment execution identity
- infrastructure provisioning identity
- operator or reviewer identity

Implemented MVP identities:

| Identity | Default account ID | Baseline roles | Purpose |
| --- | --- | --- | --- |
| Build | `secure-delivery-build` | `roles/artifactregistry.writer`, `roles/logging.logWriter` | Build, verify, log, and publish release candidate images |
| Deploy | `secure-delivery-deploy` | `roles/clouddeploy.jobRunner`, `roles/container.developer`, `roles/logging.logWriter` | Execute controlled deployment actions |
| Node | `secure-delivery-node` | `roles/logging.logWriter`, `roles/monitoring.metricWriter` | Run cluster nodes with minimal runtime telemetry permissions |
| Reviewer | `secure-delivery-reviewer` | `roles/logging.viewer`, `roles/monitoring.viewer` | Review release health and troubleshoot delivery outcomes |

The build identity can publish artifacts and write logs, but it does not receive broad deployment authority.

The deployment identity receives only the baseline permissions needed to support the controlled release path.

Operator or reviewer access supports release review and troubleshooting without requiring project-wide administrative access.
The build identity should be able to build, verify, and publish artifacts. It should not automatically receive broad deployment authority.

The deployment identity should receive only the permissions needed to deploy through the controlled release path.

Operator or reviewer access should support release review and troubleshooting without requiring project-wide administrative access.

## Kubernetes baseline

The MVP uses one GKE cluster.

The foundation creates a minimal cluster using `gke_cluster_name`, `gke_location`, `gke_initial_node_count`, and `gke_node_machine_type`.

The cluster contains three namespaces by default:
The cluster should contain three namespaces:
- `dev`
- `stage`
- `prod`

This is enough to demonstrate environment-specific trust and promotion semantics while keeping the baseline reproducible.

The baseline intentionally avoids multi-cluster topology, service mesh, and advanced Kubernetes platform abstractions.

## Foundation outputs

The foundation exposes a small set of outputs that later delivery steps can consume without coupling to Terraform internals:
- Artifact Registry repository ID, location, and Docker image prefix
- GKE cluster name and location
- environment namespaces
- build, deploy, node, and reviewer service account emails

These outputs are intended to support Cloud Build, Cloud Deploy, release metadata generation, and operator review.

## Terraform structure expectations

Prefer a clear baseline before introducing reusable modules.

The first implementation should favor:
- explicit resources
- readable variables
- minimal indirection
- environment-aware values only where needed
- comments that explain trust or release-path decisions

Avoid in the MVP:
- premature module extraction
- deep module hierarchies
- broad enterprise abstractions
- multi-cluster composition
- multi-cloud patterns

## Later extraction candidates

Reusable modules may be introduced later if repetition becomes meaningful.

Potential future modules:
- service account module
- Artifact Registry module
- Cloud Deploy helper module
- monitoring helper module

Do not over-modularize the first version. Prefer a clear baseline first.
