# Architecture Diagrams

Visual summaries of [Architecture Overview](../architecture/overview.md), [Release Model](../architecture/release-model.md), [Environment Policies](../architecture/environment-policies.md), and [IAM Model](../iam-model.md), without redefining contracts.

## Trusted delivery

```mermaid
flowchart TB
    Source[Expected source] --> Build[Image build identity]
    Build --> Registry[Artifact Registry digest]
    Registry --> Verify[Metadata gate]
    Verify --> Sign[Separate signer and KMS]
    Sign --> Trust[Validated attestation]
    Trust --> Deploy[Cloud Deploy execution identity]
    Deploy --> Admission{Binary Authorization}
    Admission -->|allowed| Runtime[GKE namespace]
    Admission -->|denied| Stop[Pod admission blocked]
```

Cloud Build executes distinct jobs; shared execution service does not combine authority. Orchestration precedes admission.

## Identity correlation

```mermaid
flowchart TB
    Source[Repository and commit] --> Build[Image build ID and identity]
    Build --> Digest[Immutable digest]
    Digest --> Verification[Verification and timestamp]
    Verification --> Trust[Attestation occurrence]
    Trust --> Release[Release and protected source hash]
    Release --> Rollout[Target rollout and approval]
    Rollout --> Runtime[Annotations and running digest]
```

Rollout state changes; artifact identity does not. Release Model owns field mapping.

## Controlled promotion

```mermaid
flowchart TB
    Release[Same rendered release] --> DevAuthorization[Separate initial dev authorization]
    DevAuthorization --> Dev[Explicit dev rollout]
    Dev --> Review[Manual dev review and fresh eligibility]
    Review --> StageAuthorization[Separate stage promotion authorization]
    StageAuthorization --> StagePending[Create stage rollout pending approval]
    StagePending --> StageApproval[Separate approval]
    StageApproval --> Stage[Stage deployment and validation]
    Stage --> ProdReview[Manual stage review and fresh eligibility]
    ProdReview --> ProdAuthorization[Separate prod promotion authorization]
    ProdAuthorization --> ProdPending[Create prod rollout pending approval]
    ProdPending --> ProdApproval[Separate approval]
    ProdApproval --> Prod[Prod deployment and validation]
```

All targets share admission. Render-all is not rollout-all; approval is separate from promotion. Failure means stop; rollback is not automatic. See [Controlled Promotion Validation](../trusted-delivery.md#controlled-promotion-validation).

## Operational visibility and review

```mermaid
flowchart LR
    Runtime[Runtime release correlation] --> Signals[Structured logs and health metrics]
    Signals --> Visibility[Dashboard and availability alert]
    Visibility --> Review[Operator review: continue or hold or reject]
```

These implemented [Observability](../observability.md) capabilities have bounded live validation. A real firing incident and broader performance validation were not completed. Automated decisions remain deferred.

## Evidence-snapshot preflight

```mermaid
flowchart TB
    Operator[Operator independently collects and reviews fresh evidence] --> Snapshot[Operator-supplied snapshot]
    Snapshot --> Evaluator[Read-only preflight evaluator]
    Evaluator --> Eligibility{READY or HOLD or BLOCKED}
    Eligibility -->|READY only| Authorization[Separate action authorization]
    Authorization --> Rollout[Cloud Deploy rollout creation]
    Rollout --> Target{Target approval required}
    Target -->|stage or prod| Approval[Separate target approval]
    Approval --> Execution[Deployment execution]
    Target -->|"dev rollback (no approval)"| Execution
```

The preflight evaluates a fresh, independently reviewed, operator-supplied evidence snapshot. It does not collect cloud data, authorize, or execute an action. Review, eligibility, action authorization, target approval, and execution remain separate boundaries; READY is eligibility only. HOLD or BLOCKED stops progression. Promotion READY and retention-driven BLOCKED were live-validated read-only; rollback eligibility and other decision scenarios have offline-only coverage. Initial dev rollout uses its separate manual review procedure. Automated promotion and rollback remain deferred.
