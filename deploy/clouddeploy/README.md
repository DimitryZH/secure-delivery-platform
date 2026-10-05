# Cloud Deploy Configuration and Preparation

## Assets and target layout

`skaffold.yaml` uses `skaffold/v4beta7`, kubectl deployment, and dev/stage/prod profiles selecting `rendered/<target>/sample-service.yaml`. `prepare-release.py` reuses `deploy/deploy-release.py`, `deploy/environments.json`, and shared base manifests to produce this bundle.

The pipeline and targets are declared in `terraform/foundation/clouddeploy.tf`: serial dev → stage → prod, with approval required for stage/prod. Every target points to `projects/<PROJECT_ID>/locations/us-central1-a/clusters/<GKE_CLUSTER>`. Profiles select namespaces; targets have no namespace field. RENDER/DEPLOY use `<DEPLOY_SERVICE_ACCOUNT>`.

## Local preparation and rendering

Preparation checks the input target and every target view before writing, rejects an existing output directory, and makes no subprocess/cloud calls. Only namespace, target annotation, and `APP_ENV` vary; candidate identity stays fixed.

```sh
python deploy/clouddeploy/prepare-release.py --metadata /local/verified-release.json --reviewed --output-dir .local-validation/bundle
cd .local-validation/bundle
skaffold diagnose -f skaffold.yaml -p dev --yaml-only
skaffold render -f skaffold.yaml -p dev --offline=true --digest-source=none --output ../render-dev.yaml
```

Repeat for stage/prod from the bundle directory, using an empty local kubeconfig. Skaffold v2.13.2 validated this schema. `--reviewed` is preparation review, not Cloud Deploy approval. Use real verified metadata for release execution; synthetic fixtures are offline only.

The source has no application build stanza, hooks, or image overrides. Preserve the exact `image@sha256:<digest>` without `--images` or `--build-artifacts`. Generated Skaffold defaults alone do not imply a rebuild; inspect actual rendering/execution. See [orchestration and rendering](../../docs/trusted-delivery.md#cloud-deploy-orchestration-and-rendering).

## Storage layout and execution limits

Source staging uses `gs://<CLOUD_DEPLOY_BUCKET>/source/<release-name>/`; target artifact storage uses `rendered/dev`, `rendered/stage`, and `rendered/prod` in that bucket. Source staging must be supplied separately from target `artifact_storage`.

The bucket uses unlocked 86400-second retention, seven-day lifecycle deletion, and seven-day soft delete, with versioning disabled and `force_destroy=false`. This finite MVP lifetime requires availability/protection review before later promotion, retry, or rollback. Never relax retention on error. The canonical [artifact protection contract](../../docs/trusted-delivery.md#source-and-rendered-artifact-protection) covers hashes, actual source URI/generation, and inherited-access limitations.

Release creation renders all profiles; it does not imply deployment to all targets. Use `--disable-initial-rollout` for reviewed creation, then separately authorize rollouts, promotion, and approval. See [Operator Runbook](../../docs/operator-runbook.md), [IAM Model](../../docs/iam-model.md), and [Controlled Promotion Validation](../../docs/trusted-delivery.md#controlled-promotion-validation).
