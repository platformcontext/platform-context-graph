# Canonical Platform Entities and End-to-End Runtime Context

## Summary

This slice expands the canonical relationship model beyond repository-to-repository
edges. `Postgres` becomes the source of truth for canonical relationship
resolution across three entity families:

- `Repository`
- `Platform`
- `WorkloadSubject`

The goal is to make PlatformContextGraph answer end-to-end questions such as:

- what deploys this service
- where deployment config is discovered
- what platform the service runs on
- what infrastructure provisions that platform
- what infrastructure provisions non-platform dependencies the service needs

This slice must work for open-source users who use the same supported tools and
languages, not only for the current local test environment. Tool semantics, not
company-specific conventions, define the canonical mapping rules.

## Problems

### Canonical truth stops at repository pairs

The current relationship resolver is repo-centric. Typed repository relationships
such as `DISCOVERS_CONFIG_IN`, `DEPLOYS_FROM`, and
`PROVISIONS_DEPENDENCY_FOR` are stored canonically in `Postgres`, but platform
semantics still live only in the graph-side workload builder.

That split creates two issues:

1. canonical truth is incomplete for runtime questions
2. “Internet to cloud to code” answers depend on graph assembly details instead
   of one explicit relationship model

### Runtime context is harder to explain than repo context

The system can now explain several repo-to-repo relationships correctly, but it
still does not have one canonical model for:

- ECS versus EKS runtime targets
- service deployment subjects
- infra repos that provision a platform versus infra repos that provision a
  service dependency
- derived dependency direction across platform chains

### Open-source portability must be explicit

The current local corpus is useful, but this repository is open source. Canonical
mapping rules must be grounded in portable tool semantics:

- Terraform and Terragrunt
- ArgoCD
- Helm
- Kustomize
- supported languages and repository layouts already handled by the indexer

The model must avoid quietly depending on one company’s naming conventions,
folder names, or environment nicknames.

### Acceptance quality for real service questions is still incomplete

`api-node-boats` is the key acceptance case because it exercises:

- OpenAPI-driven endpoint discovery
- service code and handler coverage
- related infrastructure context
- runtime and environment context
- end-to-end narrative quality in MCP-style answers

The current system can still return shallow or misleading answers when graph,
content, and runtime context are not assembled into one truthful chain.

## Goals

- make `Platform` a canonical entity in `Postgres`
- make runtime deployment subjects canonical enough to support end-to-end
  queries
- preserve typed relationship truth instead of flattening everything to
  `DEPENDS_ON`
- support both `EKS/GitOps` and `ECS/Terraform` deployment patterns
- keep completeness and partial-index truthfulness explicit in runtime and MCP
  outputs
- support open-source use through portable, tool-grounded mapping rules
- make `api-node-boats` a real acceptance target for end-to-end answer quality

## Non-Goals

- backend replacement
- provider-specific canonical entity families for every cloud service
- perfect environment inference for every deployment tool in this slice
- canonical modeling of every workload node already present in Neo4j
- rewriting all existing query surfaces at once

## Current State

### Canonical repo relationships

The canonical relationship resolver currently handles typed repo-to-repo
relationships such as:

- `DISCOVERS_CONFIG_IN`
- `DEPLOYS_FROM`
- `PROVISIONS_DEPENDENCY_FOR`

`DEPENDS_ON` is already treated as a derived compatibility edge, not as the
source truth.

### Graph-only platform semantics

The workload builder currently emits:

- `Repository -[:PROVISIONS_PLATFORM]-> Platform`
- `WorkloadInstance -[:RUNS_ON]-> Platform`

These graph edges are useful, but platform identity and platform relationships
are not yet part of the canonical Postgres resolution model.

## Design

### Canonical entity model

Add canonical relationship entities beyond repositories.

The relationship layer should store a generalized subject model with stable
identities and typed properties:

- `Repository`
  - canonical repository identity
- `Platform`
  - canonical runtime or orchestration platform
- `WorkloadSubject`
  - canonical deployable subject when the relationship must refer to something
    narrower than a repository but broader than a specific runtime instance

`WorkloadSubject` is intentionally generic. It covers cases such as:

- a service deployment subject represented by repo-backed config
- an addon or deployable component under ArgoCD/Helm/Kustomize
- future deployable workflow subjects for GitHub Actions or FluxCD

This avoids forcing all non-repo deployables into either fake repository nodes
or provider-specific object families.

### Canonical relationship vocabulary

The canonical relationship vocabulary for this slice is:

- `DISCOVERS_CONFIG_IN`
- `DEPLOYS_FROM`
- `PROVISIONS_PLATFORM`
- `RUNS_ON`
- `PROVISIONS_DEPENDENCY_FOR`

`DEPENDS_ON` remains derived only.

Direction rules:

- `DISCOVERS_CONFIG_IN`
  - source is the control-plane or orchestration subject
  - target is the repository containing discovery or environment config
- `DEPLOYS_FROM`
  - source is the deployable repo or workload subject
  - target is the repository supplying manifests, charts, overlays, or release
    artifacts
- `PROVISIONS_PLATFORM`
  - source is the infra repo or workload subject that provisions the platform
  - target is the canonical platform
- `RUNS_ON`
  - source is the deployable repo or workload subject
  - target is the canonical platform
- `PROVISIONS_DEPENDENCY_FOR`
  - source is the infra repo or workload subject
  - target is the deployable repo or workload subject whose non-platform
    dependencies it provisions

### Canonical platform model

`Platform` must be generic, not Kubernetes-only.

Portable platform identity fields:

- `platform_id`
- `kind`
  - examples: `eks`, `ecs`, `kubernetes`
- `provider`
  - examples: `aws`
- `name`
  - cluster or logical platform name when known
- `environment`
  - optional, only when grounded in tool evidence
- `region`
  - optional
- `details`
  - tool-specific metadata that remains explainable

This model must support at least:

- EKS clusters
- ECS clusters
- generic Kubernetes runtime targets when the exact managed platform is not
  safely inferable

### Workload subject model

A `WorkloadSubject` exists when the canonical relationship should refer to a
deployable thing that is not best represented as the whole repository.

Portable workload subject fields:

- `subject_id`
- `subject_type`
  - examples: `service`, `addon`, `application`
- `name`
- `repo_id`
  - nullable for future non-repo-backed subjects
- `path`
  - optional config or overlay path
- `environment`
  - optional
- `details`

In this slice, the minimum viable rule is:

- use repository-backed workload subjects only where needed for accurate
  `DEPLOYS_FROM` or `RUNS_ON` semantics
- prefer repository-level relationships when they remain truthful

### Evidence extraction rules

Evidence extraction must remain grounded in tool semantics.

#### Terraform and Terragrunt

Portable signals:

- explicit EKS or ECS resource types
- cluster module sources
- `cluster_name`
- `app_repo`
- `app_name`
- `api_configuration`
- Cloud Map service discovery configuration
- repo URLs
- deploy config objects that explicitly bind a repo to a platform or service

Typed outputs:

- infra repo `PROVISIONS_PLATFORM` platform
- service repo or workload subject `RUNS_ON` platform
- infra repo `PROVISIONS_DEPENDENCY_FOR` service repo or workload subject

#### ArgoCD

Portable signals:

- ApplicationSet git generators
- discovery `files[].path`
- `source.repoURL`
- `sources[].repoURL`
- repo-backed overlay paths

Typed outputs:

- control-plane subject `DISCOVERS_CONFIG_IN` config repo
- deployable repo or workload subject `DEPLOYS_FROM` source repo
- if platform is explicitly identified in config, workload subject `RUNS_ON`
  platform

#### Helm

Portable signals:

- `Chart.yaml`
- `values*.yaml`
- chart repository and dependency references
- release name and repo-backed config paths

Typed outputs:

- deployable repo or workload subject `DEPLOYS_FROM` source repo
- workload subject `RUNS_ON` platform when runtime evidence is explicit

#### Kustomize

Portable signals:

- `resources`
- Helm chart blocks
- images
- overlays
- remote resource URLs

Typed outputs:

- deployable repo or workload subject `DEPLOYS_FROM` source repo
- workload subject `RUNS_ON` platform when runtime evidence is explicit

Patch file names alone remain insufficient to imply deployment semantics.

### Derived compatibility `DEPENDS_ON`

Derived `DEPENDS_ON` must remain explicit and directional.

Rules:

- `DISCOVERS_CONFIG_IN`
  - derive `DEPENDS_ON` forward
- `DEPLOYS_FROM`
  - derive `DEPENDS_ON` forward
- `PROVISIONS_DEPENDENCY_FOR`
  - derive `DEPENDS_ON` in reverse so the app depends on the infra
- `RUNS_ON`
  - derive `DEPENDS_ON` forward if compatibility output is needed
- `PROVISIONS_PLATFORM`
  - do not derive repo-level `DEPENDS_ON` directly from this edge alone

Platform-chain dependency derivation should use the full typed chain, not one
edge in isolation.

### Repository completeness and MCP truthfulness

Runtime coverage remains first-class and must be preserved through this slice.

For repo summaries and MCP answers:

- never interpret root-level counts as recursive totals
- never describe missing endpoint, IaC, DNS, or environment details as “not
  present” when coverage is partial
- surface completeness state and missing domains explicitly
- keep the answer honest even when the chain is incomplete

### End-to-end answer assembly

The canonical relationship model must support answer assembly for prompts like:

- endpoints
- DNS and hostnames
- API gateway or load balancer path
- runtime platform
- environments
- deploy/config repos
- related Terraform, Terragrunt, Helm, ArgoCD, or Kustomize repos
- end-to-end path from public entrypoint to cloud runtime to code

For `api-node-boats`, the acceptance path must combine:

- OpenAPI/spec evidence
- handler/code evidence
- related infrastructure evidence
- runtime platform evidence
- deployment/config repo evidence
- truthful completeness reporting if anything is missing

## Data Model Changes

This slice requires widening the canonical relationship store beyond
repo-to-repo rows.

The design target is:

- generalized canonical entity table or equivalent typed-entity storage
- generalized relationship edges between canonical entities
- generation-scoped evidence, candidates, and resolved rows that can point to
  non-repository entities

Minimum storage capabilities:

- store repositories, platforms, and workload subjects
- store typed resolved relationships between any supported entity pair
- preserve explainable details for every canonical edge
- preserve generation activation semantics without mixed visibility

## Query Surface Changes

Repository context, repo summary, and repository stats should surface:

- related platforms
- runtime kinds and environments when grounded
- related deploy/config repos
- related infra repos
- completeness state and missing domains

These query surfaces must read from the canonical relationship model plus
runtime coverage data, not from ad hoc graph assumptions alone.

## Open Source Portability Rules

Portable rules:

- infer from tool-standard fields, not from org-local naming folklore
- keep evidence explainable from checked-in config or graph state
- use supported languages and deployment tools already handled by the repo
- degrade to partial truth instead of inventing a match

Non-portable rules that must not become canonical truth:

- repo naming assumptions that only make sense in one company
- path heuristics that only work for one monorepo or folder taxonomy
- environment aliases with no tool-grounded evidence
- opaque string matching with no stored rationale

## Edge Cases

- A service may both `DEPLOYS_FROM` another repo and `RUNS_ON` a platform.
- A control-plane repo may `DISCOVERS_CONFIG_IN` one repo while a service
  `DEPLOYS_FROM` another repo in the same chain.
- Terraform may `PROVISIONS_PLATFORM` without deploying the service.
- Terraform may also `PROVISIONS_DEPENDENCY_FOR` the same service.
- A platform may be identifiable only as generic `kubernetes` even if the
  managed control plane is unclear.
- Partial indexing must not be mistaken for absence of endpoints or IaC.
- Duplicate local checkouts must not create duplicate canonical repositories or
  duplicate canonical platforms.
- A workload subject may need to exist even when no one repository fully
  represents the deployable unit.

## Acceptance Criteria

### Canonical model

- `Platform` exists canonically in `Postgres`
- canonical resolved relationships can target `Platform` and
  `WorkloadSubject`, not only repositories
- typed relationships remain the source of truth
- derived `DEPENDS_ON` remains explicit and explainable

### EKS and ECS coverage

- an EKS GitOps chain can be represented canonically
- an ECS Terraform chain can be represented canonically
- both use the same generic `Platform` model

### Truthfulness

- repo summary and MCP outputs distinguish complete from partial coverage
- missing endpoint or IaC detail is reported as a coverage gap, not as absence
- `api-node-boats` acceptance queries either answer with grounded data or state
  exactly what is missing

### Open-source portability

- canonical mappings are based on portable tool evidence
- no canonical relationship requires Boats-specific naming conventions

## Testing Strategy

### Unit tests

- canonical entity resolution for repository, platform, and workload subject
- typed edge resolution across mixed entity families
- derived `DEPENDS_ON` direction rules
- ECS and EKS evidence extraction from portable tool patterns
- completeness-state behavior when answer assembly is partial

### Integration tests

- repository summary and repository stats include truthful platform/runtime
  context
- MCP-facing handlers expose completeness state and missing domains
- compose/runtime env propagation continues to work

### End-to-end tests

- EKS GitOps chain corpus
- ECS Terraform chain corpus
- mixed corpus with Terraform, Helm, ArgoCD, Kustomize
- negative unrelated pair remains clean
- `api-node-boats` acceptance question is answerable with truthful depth

## Rollout

This slice should be implemented in stages on the same branch:

1. extend the canonical entity model and failing tests
2. add platform and workload-subject resolution
3. wire query surfaces to the widened canonical model
4. validate on the real local corpus and the `api-node-boats` acceptance case

No phase should weaken the current coverage truthfulness guarantees.
