# PlatformContextGraph Query Model And API Design

Date: 2026-03-19
Status: Current design reference

## Summary

PlatformContextGraph should expose a first-class HTTP API and MCP surface on top of one shared query model. The system must work for code-only workflows, code-to-infrastructure workflows, and shared infrastructure scenarios where multiple workloads depend on the same resource.

The design center is:

- canonical graph model is entity-first
- canonical deployable compute unit is `Workload`
- `Service` is a public alias for the common `workload_kind=service` case
- environment-specific runtime reality is modeled as `WorkloadInstance`
- shared infrastructure remains first-class and can be consumed by many workloads
- MCP and HTTP are thin adapters over one shared Python query-service layer
- v0 requires OpenAPI, typed schemas, examples, tests, and documentation

## Goals

- Support AI-assisted development for code search, code relationships, debugging, re-architecture, and infrastructure reasoning.
- Represent both code-only repositories and code-to-cloud dependency chains.
- Model shared infrastructure correctly without forcing it under a single service.
- Expose stable HTTP endpoints that are resource-oriented rather than raw MCP tool mirrors.
- Keep MCP and HTTP behavior aligned by routing both through the same core query layer.
- Make the HTTP API self-documented via OpenAPI from day one.

## Non-Goals

- No generic public graph traversal API in v0.
- No public raw `execute_cypher_query` endpoint in v0.
- No cloud event ingestion in the core query server in v0.
- No requirement for a separate metadata repo or manually curated classification layer in v0.
- No mutable HTTP control plane for indexing, watching, or job orchestration in v0.

## Key Design Decisions

### 1. Entity-First Canonical Model

The graph must not force all meaningful context through repositories or services. Shared Terraform, Crossplane, Kubernetes, and cloud resources must be first-class entities.

Canonical entity types for v0:

- `Repository`
- `File`
- `Workload`
- `WorkloadInstance`
- `Image`
- `K8sResource`
- `TerraformModule`
- `TerraformResource`
- `CloudResource`
- `Endpoint`
- `Environment`

This model supports cases such as one shared RDS cluster consumed by multiple workloads.

Canonical IDs must be opaque, stable, and URL-safe. They are not raw filesystem paths or human names. For v0:

- `Repository.id` is a stable URL-safe identifier derived from normalized remote identity when a git remote exists, with a local-path fallback only for repos without a remote
- `Workload.id` is a stable logical identifier within the graph
- `WorkloadInstance.id` is a separate stable identifier and is not represented by adding `environment` onto a `Workload` ID
- all entity routes operate on canonical IDs, not aliases

### 2. Workload Is Canonical, Service Is Alias

External users often say "service," but `Service` is too narrow and collides semantically with Kubernetes `Service`.

Canonical runtime unit:

- `Workload`

Required subtype field:

- `workload_kind = service | worker | consumer | cronjob | batch | lambda`

Public API and MCP should expose both:

- `workload` as the canonical model
- `service` as an alias for the common case

Alias rules for v0:

- `service` resolves only to `Workload` entities where `workload_kind=service`
- `service` routes and MCP tools are convenience aliases, not separate model types
- service routes accept canonical `Workload.id` values only; fuzzy service-name lookup belongs to `resolve_entity`
- service alias responses return canonical `workload` entities and may include `requested_as=service`
- non-service workloads must not resolve from service-only routes or service-only MCP calls

### 3. Logical Workload And Environment-Specific Runtime

Both logical and environment-specific views are required.

Model:

- `Workload`: logical deployable unit
- `WorkloadInstance`: runtime/environment-specific instance

Relationship:

- `Workload HAS_INSTANCE WorkloadInstance`

This supports:

- one stable identity for "payments-api"
- precise context for "payments-api in prod"
- clean `compare_environments` behavior

HTTP and MCP surface rules:

- `/workloads/{id}/context` accepts a canonical `Workload.id`
- `/workloads/{id}/context?environment=prod` returns the matching `WorkloadInstance` view under that logical workload
- `/entities/{id}/context` accepts either a `Workload.id` or a `WorkloadInstance.id`
- `resolve_entity` may return either logical workloads or workload instances depending on the query and filters

### 4. No Separate Metadata Repo Requirement In v0

The system should infer shared infrastructure mappings from actual graph evidence:

- Terraform modules and outputs
- Kubernetes manifests and labels
- Helm values
- ConfigMaps and Secrets references
- hostnames, DSNs, ARNs, queue names, bucket names
- code references where available

Manual semantic overlays can be added later, but v0 should not depend on them.

### 5. One Shared Query Layer

HTTP and MCP must not each encode separate business logic.

Required layering:

- database/repository access
- shared query-service layer for all read/query capabilities
- deployment-managed indexing/runtime layer
- MCP adapter
- HTTP adapter

All inference, scoring, and response assembly must live below the adapters.

## Core Graph Relationships

Representative relationships for v0:

- `Repository CONTAINS File`
- `File DEFINES Workload`
- `File DEFINES TerraformModule`
- `File DEFINES TerraformResource`
- `File DEFINES K8sResource`
- `Repository DEFINES Workload`
- `Workload HAS_INSTANCE WorkloadInstance`
- `Repository BUILDS Image`
- `WorkloadInstance RUNS_IMAGE Image`
- `WorkloadInstance DEPLOYED_AS K8sResource`
- `TerraformModule DEFINES TerraformResource`
- `TerraformResource PROVISIONS CloudResource`
- `WorkloadInstance CONFIGURED_BY File`
- `WorkloadInstance REFERENCES CloudResource`
- `File REFERENCES CloudResource`
- `File REFERENCES Endpoint`
- `WorkloadInstance USES CloudResource`
- `WorkloadInstance EXPOSES Endpoint`
- `Workload DEPENDS_ON Workload`
- `WorkloadInstance DEPENDS_ON WorkloadInstance`
- `WorkloadInstance IN_ENVIRONMENT Environment`

The important many-to-many case is preserved:

- many `WorkloadInstance` nodes can `USE` the same `CloudResource`
- many `Repository` nodes can map to one shared infrastructure resource through evidence-backed edges

Query services must prefer direct instance-to-instance or instance-to-resource edges when an environment is specified. Logical workload-level edges are fallbacks and should carry lower confidence when they stand in for missing instance-level evidence.

## Shared Query Primitives

These are the canonical query services that both MCP and HTTP will call.

### Context Query Services

- `resolve_entity`
- `get_entity_context`
- `get_workload_context`
- `get_service_context` as alias
- `trace_resource_to_code`
- `explain_dependency_path`
- `find_change_surface`
- `compare_environments`

### Code Query Services

- `search_code`
- `get_code_relationships`
- `find_dead_code`
- `get_complexity`
- `get_repository_context`
- `get_repository_stats`

### Infrastructure Query Services

- `search_infra_resources`
- `get_infra_relationships`
- `get_ecosystem_overview`

For v0, every documented read/query HTTP endpoint and every documented read/query MCP tool must route through these shared query services. Existing handler code may be adapted incrementally, but no documented v0 query surface should bypass the shared query layer.

## HTTP API v0

All HTTP endpoints must be versioned under `/api/v0`.

### Code API

These endpoints preserve code-focused workflows for developers who do not need infrastructure context.

- `POST /api/v0/code/search`
- `POST /api/v0/code/relationships`
- `POST /api/v0/code/dead-code`
- `POST /api/v0/code/complexity`
- `GET /api/v0/repositories/{id}/context`
- `GET /api/v0/repositories/{id}/stats`

### Context API

- `POST /api/v0/entities/resolve`
- `GET /api/v0/entities/{id}/context`
- `GET /api/v0/workloads/{id}/context`
- `GET /api/v0/services/{id}/context`
- `POST /api/v0/traces/resource-to-code`
- `POST /api/v0/paths/explain`
- `POST /api/v0/impact/change-surface`
- `POST /api/v0/environments/compare`

Route parameter rules:

- `/repositories/{id}/...` accepts canonical opaque `Repository.id`, not raw filesystem paths
- `/workloads/{id}/...` accepts canonical `Workload.id`
- `/services/{id}/...` accepts canonical `Workload.id` where `workload_kind=service`
- fuzzy names, partial names, and non-canonical identifiers should be normalized through `POST /api/v0/entities/resolve`

### Infrastructure API

- `POST /api/v0/infra/resources/search`
- `POST /api/v0/infra/relationships`
- `GET /api/v0/ecosystem/overview`

`/infra/resources/search` is a scoped convenience search over infrastructure entity types. It must return the same canonical entity IDs as `/entities/resolve` and should be implemented on top of the same normalization and ranking logic with infra-specific defaults.

There is no public HTTP control API in v0. Indexing remains CLI-driven locally and deployment-managed in Kubernetes via bootstrap indexing and repo-sync runtime components.
- `GET /api/v0/repositories`

### OpenAPI And Docs

Required in v0:

- `GET /api/v0/openapi.json`
- `GET /api/v0/docs`
- `GET /api/v0/redoc`

## MCP Surface v0

The MCP surface should expose the same core capabilities via tool-friendly contracts:

- `resolve_entity`
- `get_entity_context`
- `get_workload_context`
- `get_service_context`
- `trace_resource_to_code`
- `explain_dependency_path`
- `find_change_surface`
- `compare_environments`

For v0, all documented read/query MCP capabilities, including code-focused and infrastructure-focused ones, should route through the shared query services above. Command-style operations such as indexing and watching may continue to use a separate command/control service layer.

## Request And Response Model Rules

### Canonical Identity

All APIs should accept and return stable entity references.

Example:

```json
{
  "id": "workload:payments-api",
  "type": "workload",
  "kind": "service",
  "name": "payments-api"
}
```

Environment-specific runtime identity uses a separate entity:

```json
{
  "id": "workload-instance:payments-api:prod",
  "type": "workload_instance",
  "workload_id": "workload:payments-api",
  "kind": "service",
  "environment": "prod",
  "name": "payments-api"
}
```

Repository identity also uses a canonical opaque ID:

```json
{
  "id": "repository:r_ab12cd34",
  "type": "repository",
  "name": "payments-api",
  "path": "/srv/repos/payments-api"
}
```

### Workload Context Behavior

- `/workloads/{id}/context` returns the logical workload view
- `/workloads/{id}/context?environment=prod` returns the environment-specific instance view
- `/services/{id}/context` is an alias to workload context
- `/services/{id}/context` only resolves workloads where `workload_kind=service`
- alias routes return canonical workload-shaped responses, not a distinct `service` entity type
- when an environment-specific instance is selected, the response should include both the logical workload and the resolved workload instance

### Entity Resolution Behavior

`resolve_entity` is the front door for fuzzy or user-supplied identifiers.

Request contract for v0:

- required `query: string`
- optional `types: EntityType[]`
- optional `kinds: string[]`
- optional `environment: string`
- optional `repo_id: string`
- optional `exact: boolean`, default `false`
- optional `limit: integer`, default `10`

Behavior rules for v0:

- returns a ranked candidate set, not a single forced match
- exact mode disables fuzzy expansion and only returns canonical or exact textual matches
- non-exact mode may use names, labels, paths, hostnames, ARNs, queue names, bucket names, and known aliases
- results must always return canonical entity refs and scores
- ambiguous results are represented as multiple ranked matches, not silent coercion
- service-name lookups and workload-name lookups normalize onto canonical `Workload.id`
- repository lookup may match by repo name or known path but always returns canonical `Repository.id`

### Evidence And Confidence

Every inferred edge and every response that depends on inference must carry:

- `confidence`
- `reason`
- `evidence`

Example evidence sources:

- Helm values
- Kubernetes env vars
- Terraform outputs
- module references
- code references

This is required so AI consumers can distinguish strong mappings from weaker inferred ones.

### Errors

HTTP errors should use one consistent typed structure, preferably RFC 7807 style problem details.

## Documentation Requirements

The API is not complete in v0 without documentation.

Required documentation artifacts:

- OpenAPI-generated HTTP reference
- human-written guides for major query workflows
- examples for shared infrastructure scenarios
- examples for code-only workflows
- docs that explain `workload` vs `service`
- docs that explain logical workloads vs `WorkloadInstance`

At least one reference scenario must be documented end-to-end:

- shared RDS cluster
- Terraform module provisioning it
- multiple workloads consuming it
- tracing the dependency path back to repos and config

## Testing Requirements

v0 must include:

- unit tests for query services
- HTTP integration tests for all documented endpoints
- OpenAPI contract tests against live responses
- alias tests proving `/services/...` and `/workloads/...` stay aligned
- fixture-based tests for shared infrastructure scenarios
- fixture-based tests for code-only scenarios

The HTTP API should not be considered stable until the OpenAPI schema and integration tests agree.

## Proposed Internal Package Layout

```text
src/platform_context_graph/
  domain/
  query/
  api/
  mcp/
  runtime/
  tools/
  core/
```

Suggested responsibility split:

- `domain/`: typed entities, enums, shared request/response models
- `query/`: canonical query services, including `context/`, `impact/`, and `repositories/` subpackages
- `api/`: FastAPI app and routers
- `mcp/`: MCP adapters and tool wiring
- `runtime/`: bootstrap indexing and repo-sync orchestration
- `tools/`: graph-building, parsing, and analysis helpers
- `core/`: graph/database access helpers and low-level runtime primitives

## v0 Implementation Order

1. Introduce typed domain models.
2. Extract a shared query-service layer from current handler logic.
3. Implement `resolve_entity`.
4. Implement `get_entity_context`.
5. Implement `get_workload_context`.
6. Add `get_service_context` alias behavior.
7. Implement trace, impact, and compare services.
8. Add FastAPI routers and OpenAPI generation.
9. Wire MCP adapters to the same query services.
10. Add API docs, examples, integration tests, and contract tests.

## Open Questions For Planning

- Which current MCP handlers can be lifted directly into shared query services versus needing redesign?
- Which existing HTTP SSE transport code should be reused versus isolated from the new API app?
- Which existing code-focused handlers can be adapted with minimal schema changes after extraction into shared query services?

## Decision

Proceed with planning around:

- entity-first graph model
- canonical `Workload` plus `WorkloadInstance`
- `Service` as public alias
- first-class HTTP API documented by OpenAPI in v0
- separate code, context, infrastructure, and control API groupings
- one shared query layer under both MCP and HTTP
