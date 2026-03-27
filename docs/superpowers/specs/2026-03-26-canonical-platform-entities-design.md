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
- `locator`
  - optional provider- or tool-grounded stable identifier such as cluster ARN,
    cluster URL, or other canonical external reference
- `details`
  - tool-specific metadata that remains explainable

Deterministic v1 platform identity rule:

- derive a canonical platform key from normalized
  `(kind, provider, locator-or-name, environment, region)`
- set
  `platform_id = platform:<kind>:<provider-or-none>:<locator-or-name-or-none>:<environment-or-none>:<region-or-none>`
- normalize empty values to `none`
- a platform candidate may become canonical only if it has at least one stable
  discriminator beyond `kind` and `provider`:
  - `locator`, or
  - `name`, or
  - both `environment` and `region`
- if a candidate lacks that discriminator, keep it as a candidate only and do
  not publish a canonical platform edge
- do not rewrite an existing canonical platform from `kubernetes` to `eks` or
  `ecs` in place
- instead, keep platform candidates separate until resolution selects one
  canonical identity for the active generation

v1 candidate merge and promotion rules:

- merge platform candidates only when normalized `provider`, `name`,
  `locator`, `environment`, and `region` match and `kind` is equal
- `kubernetes` may promote to `eks` only when the same candidate also has
  explicit EKS evidence from portable signals
- `kubernetes` may promote to `ecs` only when the same candidate also has
  explicit ECS evidence from portable signals
- if promotion would change more than `kind`, do not merge automatically
- if conflicting platform kinds or providers remain after normalization, keep
  candidates unresolved and do not publish a canonical platform edge

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

Exact v1 creation rule:

Create a `WorkloadSubject` only when at least one of these is true:

1. one repository contains multiple independently deployable subjects that must
   not share one canonical runtime or deployment edge
2. one config repo contains distinct deployable add-ons or services identified
   by stable tool-grounded fields such as addon name, release name, or overlay
   path
3. one repository maps to different deployable runtime subjects by environment
   or platform target in a way that would make repository-level `RUNS_ON` or
   `DEPLOYS_FROM` misleading

If none of those conditions are true, use the repository entity itself.

v1 identity rule:

- `subject_id = workload-subject:<repo-id-or-none>:<subject-type>:<normalized-name>:<environment-or-none>:<normalized-path-or-none>`

v1 examples:

- `api-node-boats`
  - one service per repo
  - repository entity is sufficient
- `helm-charts` deploying `api-node-bw-home`
  - no `WorkloadSubject` needed for `api-node-bw-home -> DEPLOYS_FROM -> helm-charts`
- `iac-eks-observability` with addon overlays such as `grafana`
  - create `WorkloadSubject` for `addon:grafana:ops-qa` when runtime or deploy
    semantics differ by addon/environment
- a Kustomize repo with both `payments` and `auth` overlays
  - create one `WorkloadSubject` per deployable overlay subject

### Evidence extraction rules

Evidence extraction must remain grounded in tool semantics.

#### Terraform and Terragrunt

Portable canonical signals:

- explicit EKS or ECS resource types
- cluster module sources that are tool- or provider-standard enough to identify
  a platform kind
- `cluster_name` only when paired with an explicit platform resource or module
  signal
- Cloud Map service discovery configuration when paired with ECS
  service/module evidence
- repo URLs
- deploy config objects that explicitly bind a repo to a platform or service
  through checked-in config

Heuristic-only signals that may create candidates but must not publish
canonical truth on their own:

- `app_repo`
- `app_name`
- `api_configuration`
- org-local variable names or wrapper-module fields without a second portable
  corroborating signal

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

v1 derivation matrix:

| Canonical edge | Derived `DEPENDS_ON` | Notes |
| --- | --- | --- |
| `A DISCOVERS_CONFIG_IN B` | `A DEPENDS_ON B` | forward |
| `A DEPLOYS_FROM B` | `A DEPENDS_ON B` | forward |
| `A PROVISIONS_DEPENDENCY_FOR B` | `B DEPENDS_ON A` | reverse because the app depends on the infra |
| `A RUNS_ON P` | `A DEPENDS_ON P` | forward to platform entity |
| `A PROVISIONS_PLATFORM P` | none by itself | requires chain context |

v1 multi-hop derivation rule:

If:

- `S RUNS_ON P`
- `I PROVISIONS_PLATFORM P`

then derive:

- `S DEPENDS_ON I`

This chain-derived compatibility edge exists only when:

- both typed edges are canonical in the active generation
- `P` is the same canonical platform entity
- there is no explicit rejection for the derived pair

Example:

- `api-node-boats RUNS_ON platform:aws:ecs:node10`
- `terraform-stack-ecs PROVISIONS_PLATFORM platform:aws:ecs:node10`
- derived compatibility edge:
  - `api-node-boats DEPENDS_ON terraform-stack-ecs`

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

Boundary for this slice:

- DNS, hostname, API gateway, and load-balancer path are not new canonical
  entities in this slice
- those facts continue to come from existing indexed graph/content evidence and
  repository context assembly
- if that evidence is absent or partial, the system must return `dns_unknown`
  and/or `entrypoint_unknown` rather than pretending the service has no such
  entrypoint
- this slice guarantees truthful reporting and typed runtime/deployment chains,
  not universal entrypoint inference for every supported tool

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

The v1 storage shape is explicit:

- `relationship_entities`
  - canonical entity registry
  - one row per canonical `Repository`, `Platform`, or `WorkloadSubject`
- `relationship_candidates`
  - generation-scoped candidate edges using generalized entity ids
- `resolved_relationships`
  - generation-scoped canonical and derived edges using generalized entity ids
- `relationship_evidence_facts`
  - generation-scoped evidence using generalized entity ids when already known,
    or typed unresolved references when evidence must be resolved first
- `relationship_assertions`
  - generalized entity assertions and rejections

`relationship_checkouts` remains repo-only because it tracks filesystem
checkouts, not canonical non-repository entities.

v1 `relationship_entities` columns:

- `entity_id` primary key
- `entity_type` in `Repository | Platform | WorkloadSubject`
- `repository_id` nullable
- `subject_type` nullable
- `kind` nullable
- `provider` nullable
- `name`
- `environment` nullable
- `path` nullable
- `region` nullable
- `locator` nullable
- `details` jsonb
- `created_at`
- `updated_at`

v1 uniqueness rules:

- `Repository`
  - unique by canonical repository id
- `Platform`
  - unique by `(kind, provider, locator, name, environment, region)` after
    normalization
- `WorkloadSubject`
  - unique by `(repository_id, subject_type, name, environment, path)` after
    normalization

v1 migration rule:

- phase 1: add `relationship_entities` and additive nullable `source_entity_id`
  / `target_entity_id` columns alongside existing repo-id columns
- phase 2: backfill repository entities from existing canonical repository
  identities
- phase 3: backfill entity-id columns for existing evidence, candidate,
  resolved, and assertion rows that are still repo-backed
- phase 4: switch new writes to entity ids while keeping repo-id reads
  compatible for rollback
- phase 5: switch projection and query surfaces to entity-id reads after
  verification on an active generation
- phase 6: only then consider tightening nullability or removing deprecated
  repo-only reads in a later slice

Compatibility and rollback rule:

- existing assertions and resolved rows remain valid during migration because
  repository entities are backfilled first
- if entity backfill or projection validation fails, continue reading the last
  known-good active generation through existing repo-compatible paths
- no migration step may invalidate the current active generation before the
  replacement generation is fully verified

v1 activation rule:

- entity rows are not generation-scoped
- candidate and resolved rows remain generation-scoped
- activation still swaps one generation at a time, so mixed entity families do
  not create mixed-generation visibility

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

v1 repository query contract:

- `get_repo_summary`
  - must return an object with:
    - `coverage`
      - `{ completeness_state, discovered_file_count, graph_recursive_file_count, root_file_count, content_file_count, content_entity_count, graph_gap_count, content_gap_count, server_content_available }`
    - `platforms`
      - array of
        `{ entity_id, kind, provider, name, environment, region, relationship_type }`
    - `deploys_from`
      - array of
        `{ entity_id, entity_type, name, environment, relationship_type }`
    - `discovers_config_in`
      - array of
        `{ entity_id, entity_type, name, environment, relationship_type }`
    - `provisioned_by`
      - array of
        `{ entity_id, entity_type, name, environment, relationship_type }`
    - `provisions_dependencies_for`
      - array of
        `{ entity_id, entity_type, name, environment, relationship_type }`
    - `environments`
      - array of normalized environment strings grounded in canonical entities
        or coverage rows
    - `limitations`
      - array of stable limitation codes
- `get_repository_stats`
  - must return existing code/file/entity counts plus:
    - `coverage`
    - `platform_count`
    - `deployment_source_count`
    - `environment_count`
    - `limitations`
- `get_repository_context`
  - must return an object with:
    - `summary`
      - repository-centered narrative fields already exposed today
    - `coverage`
      - same `coverage` contract as `get_repo_summary`
    - `platforms`
      - same `platforms` contract as `get_repo_summary`
    - `deployment_chain`
      - ordered typed relationships needed to explain deploy/config/runtime flow
    - `iac_relationships`
      - typed infra relationships relevant to the repository
    - `environments`
      - same normalized environment array as `get_repo_summary`
    - `limitations`
      - same stable limitation codes as `get_repo_summary`
- repository context assembly
  - must aggregate canonical repo/entity relationships back into a
    repository-centered summary without dropping typed semantics

v1 limitations contract:

Add these values only when their trigger condition is true:

- `content_partial`
  - `content_gap_count > 0`
- `graph_partial`
  - `graph_gap_count > 0`
- `endpoint_specs_missing`
  - service-like repo has no indexed OpenAPI/spec evidence and coverage is
    otherwise complete for expected spec paths
- `runtime_platform_unknown`
  - no canonical `RUNS_ON` platform is resolved for the repo or its workload
    subjects
- `deployment_chain_incomplete`
  - deployment/config relationship evidence exists but no complete canonical
    chain can be assembled
- `iac_relationships_incomplete`
  - infra-related evidence exists but no canonical provisioning relationship can
    be resolved
- `dns_unknown`
  - the answer requested DNS/hostname context and no grounded DNS evidence is
    available
- `entrypoint_unknown`
  - the answer requested ingress, API gateway, or load-balancer path context
    and no grounded entrypoint evidence is available

The answer layer may summarize these, but must not invent absence.

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

Portable tool boundary for v1:

- Terraform
- Terragrunt
- ArgoCD
- Helm
- Kustomize

GitHub Actions and FluxCD remain follow-on mappings. The canonical entity model
must not block them, but this slice does not require implementing them.

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

Ambiguity and conflict rules:

- if both `ecs` and `kubernetes` are inferred for the same platform candidate,
  keep the more specific managed platform (`ecs`)
- if both `eks` and generic `kubernetes` are inferred for the same platform
  candidate, keep `eks`
- if two platform candidates disagree on provider or platform kind and cannot be
  merged safely, do not publish a canonical platform edge; keep candidates only
- if environment is ambiguous, leave it null instead of guessing
- explicit assertion may promote one candidate platform identity
- explicit rejection blocks one canonical edge without deleting the underlying
  evidence

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

### Planning unit A: canonical entities and resolution

1. extend the canonical entity model and failing tests
2. add platform and workload-subject resolution
3. preserve active-generation projection and compatibility behavior

### Planning unit B: query and MCP rollout

1. wire query surfaces to the widened canonical model
2. implement `api-node-boats` acceptance coverage and answer assembly
3. validate on the real local corpus and the `api-node-boats` acceptance case

No phase should weaken the current coverage truthfulness guarantees.

### Neo4j compatibility boundary

Neo4j remains the read-model projection during this slice.

v1 projection contract:

- project canonical `Repository`, `Platform`, and `WorkloadSubject` nodes
- project typed edges among those nodes
- keep existing repository-centered query paths working by:
  - projecting derived compatibility `DEPENDS_ON` edges
  - allowing repository summary surfaces to aggregate subject/platform facts back
    to repository views
- do not remove existing repo-only read paths until the new projection-backed
  queries are verified
