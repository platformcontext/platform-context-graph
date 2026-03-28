# HTTP API Reference

The HTTP API is versioned under `/api/v0` and shares the same query model as CLI and MCP. It is intended for AI agents, automation, and internal tools that need a stable contract.

## OpenAPI is the source of truth

The live OpenAPI spec is always canonical. If this page and the spec disagree, the spec wins.

- `GET /api/v0/openapi.json` — machine-readable schema
- `GET /api/v0/docs` — Swagger UI
- `GET /api/v0/redoc` — ReDoc

## Scope

The public HTTP API exposes two surfaces:

- a read/query surface for context, code, infra, and content retrieval
- a small ingester control surface for runtime status and manual scan requests

Use it to resolve entities, fetch context, search code, trace infra, compare environments, and inspect the deployed ingester state.

Use the CLI for local indexing workflows. Use the Helm runtime for deployment-managed repository ingestion and steady-state sync.

## Model Basics

- `workload` is the canonical deployable compute model.
- `service` is a convenience alias over workloads with `kind=service`.
- environment-scoped calls return the logical workload plus the resolved `WorkloadInstance`.
- canonical entity IDs are required on path-based context routes.
- repository identity is remote-first when a git remote exists.
- repository objects expose `repo_slug`, `remote_url`, and `local_path`.
- `local_path` is server-local metadata, not a portable client filesystem path.
- file-bearing query results should be interpreted using `repo_id + relative_path`, not an absolute server path.
- `repo_access` indicates whether the caller may need to ask the user for a local checkout path or clone decision.

## Context API

### Resolve fuzzy input into canonical entities

`POST /api/v0/entities/resolve`

Use this before context lookups when the caller has a fuzzy name, alias, or partial resource description.

```json
{
  "query": "payments prod rds",
  "types": ["workload", "cloud_resource"],
  "environment": "prod",
  "limit": 5
}
```

### Get canonical entity context

`GET /api/v0/entities/{id}/context`

Examples:

- `GET /api/v0/entities/workload:payments-api/context`
- `GET /api/v0/entities/workload-instance:payments-api:prod/context`

### Get workload context

`GET /api/v0/workloads/{id}/context`

Logical view:

- `GET /api/v0/workloads/workload:payments-api/context`

Environment-scoped view:

- `GET /api/v0/workloads/workload:payments-api/context?environment=prod`

### Get service context

`GET /api/v0/services/{id}/context`

This is an alias route. It still accepts a canonical workload ID:

- `GET /api/v0/services/workload:payments-api/context`
- `GET /api/v0/services/workload:payments-api/context?environment=prod`

Service alias responses include `requested_as=service`.

## Story API

Use the story routes when the caller wants a structured narrative first and
evidence second.

Story responses are shaped around:

- `subject`
- `story`
- `story_sections`
- `deployment_overview` or `code_overview`
- `evidence`
- `limitations`
- `coverage`
- `drilldowns`

HTTP story routes stay canonical-ID based. If the caller starts with a fuzzy
name or alias, resolve first and then call the story route.

### Get repository story

`GET /api/v0/repositories/{id}/story`

Example:

- `GET /api/v0/repositories/repository:r_ab12cd34/story`

### Get workload story

`GET /api/v0/workloads/{id}/story`

Examples:

- `GET /api/v0/workloads/workload:payments-api/story`
- `GET /api/v0/workloads/workload:payments-api/story?environment=prod`

### Get service story

`GET /api/v0/services/{id}/story`

Examples:

- `GET /api/v0/services/workload:payments-api/story`
- `GET /api/v0/services/workload:payments-api/story?environment=prod`

Treat the story routes as the top-level contract for repo/service/workload
narratives. Use the context routes, trace routes, and content routes named in
`drilldowns` for follow-up evidence.

## Code API

Use these routes when you only need code relationships and do not need the full code-to-cloud graph.

- `POST /api/v0/code/search`
- `POST /api/v0/code/relationships`
- `POST /api/v0/code/dead-code`
- `POST /api/v0/code/complexity`

Public code-query requests use canonical `repo_id` whenever a repository scope
is part of the request. Results should be interpreted using `repo_id +
relative_path`, not absolute server-local paths.

Example code-only workflow:

`POST /api/v0/code/search`

```json
{
  "query": "process_payment",
  "repo_id": "repository:r_ab12cd34",
  "exact": false,
  "limit": 10
}
```

Example dead-code workflow:

`POST /api/v0/code/dead-code`

```json
{
  "repo_id": "repository:r_ab12cd34",
  "scope": "repo"
}
```

## Content API

Use these routes when a caller needs source text or indexed content search without relying on raw server filesystem paths.

- `POST /api/v0/content/files/read`
- `POST /api/v0/content/files/lines`
- `POST /api/v0/content/entities/read`
- `POST /api/v0/content/files/search`
- `POST /api/v0/content/entities/search`

Rules:

- portable file lookup uses `repo_id + relative_path`
- portable entity lookup uses `entity_id`
- deployed API runtimes are PostgreSQL-first and PostgreSQL-only for direct content reads
- if PostgreSQL is disabled or missing a cached row, deployed HTTP reads return `source_backend=unavailable` instead of reading from a server workspace checkout
- local CLI and non-deployed helper flows may still use workspace or graph-cache fallbacks
- file and entity read responses include `source_backend` so callers can see whether the result came from `postgres`, `workspace`, `graph-cache`, or `unavailable`
- content search routes require the PostgreSQL content store and return an error payload when it is disabled
- content retrieval should not trigger `repo_access` prompting when the server already has the checkout

Example file read:

```json
{
  "repo_id": "repository:r_ab12cd34",
  "relative_path": "src/payments.py"
}
```

Example entity read:

```json
{
  "entity_id": "content-entity:e_ab12cd34ef56"
}
```

Example file-content search:

```json
{
  "pattern": "shared-payments-prod",
  "repo_ids": ["repository:r_ab12cd34"]
}
```

## Infra API

- `POST /api/v0/infra/resources/search`
- `POST /api/v0/infra/relationships`
- `GET /api/v0/ecosystem/overview`
- `POST /api/v0/traces/resource-to-code`
- `POST /api/v0/paths/explain`
- `POST /api/v0/impact/change-surface`
- `POST /api/v0/environments/compare`

These routes are for tracing shared infrastructure, blast radius, dependency explanation, and environment drift.

## Repository API

- `GET /api/v0/repositories`
- `GET /api/v0/repositories/{id}/context`
- `GET /api/v0/repositories/{id}/story`
- `GET /api/v0/repositories/{id}/stats`

Repository routes also require canonical repository IDs.

Repository responses should be treated as:

- canonical identity: `id`
- remote identity: `repo_slug`, `remote_url`
- server-local checkout metadata: `local_path`

If a downstream workflow needs local file operations on a user machine, use `repo_access` or ask the user for a local checkout path instead of assuming the server path exists locally.

For local or deployed indexing workflows, use the CLI and deployment runtime:

- local: `pcg index <path>`
- Kubernetes: repository ingestion is deployment-managed through the ingester runtime

## Ingester API

Use these routes to inspect or control deployed ingesters without reaching into Kubernetes directly.

- `GET /api/v0/ingesters`
- `GET /api/v0/ingesters/{ingester}`
- `POST /api/v0/ingesters/{ingester}/scan`

The default ingester is `repository`.

Status responses are designed for remote operation and include:

- ingester identity
- current status
- active run id
- last attempt / last success
- next retry timing
- repository progress counts
- failure counts and last error details

Manual scan requests are persisted for the ingester runtime to claim asynchronously; the API does not perform the scan inline.

## Bundle Import API

Use this route when you want to load dependency or library internals explicitly
without indexing vendored source trees as part of the normal repository scan.

- `POST /api/v0/bundles/import`

Request contract:

- `multipart/form-data`
- file field: `bundle`
- optional form field: `clear_existing=true|false`

The route imports the uploaded `.pcg` bundle into the active graph database and
returns the same success/message shape as the CLI bundle import flow.
