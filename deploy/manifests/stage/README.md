# Stage deployment

Use the shared base manifests through [the deployment CLI](../../../docs/trusted-delivery.md#environment-aware-deployment).
Stage requires the same verified digest, matching target_environment, and explicit --reviewed.
Review the previous environment before execution; no automatic promotion is implemented.
