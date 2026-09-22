# Architecture Diagrams

This page is the visual index for the Secure Delivery Platform architecture.

The diagrams describe the canonical design and trust model, not the current deployment state. The Trusted Release Model defines the architecture; the executable foundation, trust enforcement, controlled promotion, and operational visibility are implemented incrementally according to the roadmap.

For the detailed design, see the [Architecture Overview](../architecture/overview.md), [Release Metadata Contract](../architecture/release-metadata.md), [Trust Model](../architecture/trust-model.md), and [Environment Policies](../architecture/environment-policies.md).

## Platform architecture

This diagram shows the intended Google Cloud component boundaries and the direction of release and operational evidence.

```mermaid
flowchart LR
    Source[Source repository] --> Build[Cloud Build]
    Build --> Registry[Artifact Registry]
    Registry --> Verify[Verification gate]
    Verify --> Trust[Trust signal]
    Trust --> Deploy[Cloud Deploy]
    Deploy --> Admission[Binary Authorization]
    Admission --> Runtime[GKE namespaces]
    Runtime --> Observe[Cloud Monitoring and Logging]
    Observe --> Decision[Release decision]
    Decision --> Deploy

    Metadata[Release metadata] -. records identity .-> Build
    Build -. updates .-> Metadata
    Verify -. updates .-> Metadata
    Deploy -. updates .-> Metadata
    Runtime -. correlates .-> Metadata
```

## Trusted release path

The release path separates artifact creation from deploy eligibility. A failed verification or policy evaluation stops progression without changing the candidate identity.

```mermaid
flowchart LR
    S[Source] --> B[Build]
    B --> A[Artifact by digest]
    A --> V{Verify}
    V -->|passed| T[Trust signal]
    V -->|failed| StopV[Ineligible candidate]
    T --> P{Target policy}
    P -->|eligible| D[Deploy]
    P -->|denied| StopP[Deployment blocked]
    D --> O[Observe]
    O --> R{Promotion decision}
    R -->|continue| Next[Promote same digest]
    R -->|hold or reject| StopR[Hold or rollback]
```

## Release identity and metadata flow

Canonical snake_case metadata fields connect each stage. Kubernetes annotations use the `release.secure-delivery.dev` namespace and map back to these canonical keys.

```mermaid
flowchart LR
    SourceFields["source_repository<br/>commit_sha"] --> BuildFields["build_id<br/>build_service_account"]
    BuildFields --> ArtifactFields["image_uri<br/>image_digest"]
    ArtifactFields --> VerificationFields["verification_status<br/>verification_timestamp<br/>trust_signal_ref"]
    VerificationFields --> PromotionFields["release_name<br/>target_environment<br/>promotion_state"]
    PromotionFields --> RuntimeFields["runtime annotations<br/>deployed namespace<br/>running digest"]

    Identity[One release candidate identity] --- SourceFields
    Identity --- ArtifactFields
    Identity --- RuntimeFields
```

## Trust boundaries and service identities

The MVP separates production of an artifact from authority to deploy it. Operator access is read-oriented, while infrastructure provisioning remains a separate administrative responsibility.

```mermaid
flowchart LR
    Source[Expected source change] --> Trigger[Controlled build trigger]

    subgraph BuildBoundary[Build boundary]
        BuildSA[Build and verification identity]
        BuildJob[Build and verification work]
        BuildSA --> BuildJob
    end

    subgraph ArtifactBoundary[Artifact boundary]
        Registry[Approved Artifact Registry repository]
        Digest[Immutable image digest]
        Registry --> Digest
    end

    subgraph DeploymentBoundary[Deployment boundary]
        DeploySA[Deployment identity]
        Policy[Binary Authorization policy]
        Cluster[GKE target namespace]
        DeploySA --> Policy
        Policy --> Cluster
    end

    subgraph ReviewBoundary[Operational review boundary]
        Reviewer[Reviewer identity]
        Telemetry[Cloud Logging and Monitoring]
        Reviewer --> Telemetry
    end

    Trigger --> BuildSA
    BuildJob --> Registry
    Digest --> Policy
    Cluster --> Telemetry
```

## Environment promotion flow

Promotion preserves the release identity and immutable digest. Each target applies its own policy and runtime review before the next explicit promotion.

```mermaid
flowchart LR
    Candidate["Verified release candidate<br/>image@sha256:digest"] --> DevGate{Dev policy}
    DevGate -->|eligible| Dev[Dev]
    Dev --> DevReview{Runtime review}
    DevReview -->|continue| StageGate{Stage promotion gate}
    DevReview -->|hold or reject| DevStop[Hold or rollback]
    StageGate -->|eligible| Stage[Stage]
    StageGate -->|blocked| StageStop[Promotion blocked]
    Stage --> StageReview{Runtime review}
    StageReview -->|continue| ProdGate{Prod promotion gate}
    StageReview -->|hold or reject| StageStop
    ProdGate -->|eligible| Prod[Prod]
    ProdGate -->|blocked| ProdStop[Promotion blocked]

    Identity[Same release identity and digest] -. preserved .-> Dev
    Identity -. preserved .-> Stage
    Identity -. preserved .-> Prod
```
