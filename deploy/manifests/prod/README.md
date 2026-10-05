# Prod deployment

Use the shared base manifests through [the deployment CLI](../../../docs/trusted-delivery.md#environment-aware-deployment).
Prod requires the same verified digest, matching target_environment, and explicit --reviewed.
Review the stage runtime outcome before execution; no automatic promotion is implemented.
