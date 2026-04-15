# HTTP API Reference

The HTTP API is versioned under `/api/v0` and shares the same query model as CLI and MCP. It is intended for AI agents, automation, and internal tools that need a stable contract.

## OpenAPI is the source of truth

The live OpenAPI spec is always canonical. If this page and the spec disagree, the spec wins.

- `GET /api/v0/openapi.json` — machine-readable schema
- `GET /api/v0/docs` — Swagger UI
- `GET /api/v0/redoc` — ReDoc

For the mounted Go runtime admin surface, the checked-in OpenAPI contract lives
in `docs/openapi/runtime-admin-v1.yaml`. That contract is separate from the
public `/api/v0` schema because it belongs to the long-running runtime admin
endpoints, not the public query API.

## Scope

The public HTTP API exposes three operator-relevant surfaces:

- a read/query surface for context, code, infra, and content retrieval
- a small ingester control surface for runtime status and manual scan requests
- a checkpoint surface for index completeness and admin reindex requests

Use it to resolve entities, fetch context, search code, trace infra, compare environments, and inspect the deployed ingester state.

Use the CLI for local indexing workflows. Use the Helm runtime for
deployment-managed repository ingestion and steady-state sync.

## Health, Status, And Completeness

Health checks answer whether a process can serve. Completeness checks answer
whether the latest published Go checkpoint is finished.

- `GET /health` reports API process health after dependency
  initialization. It does not prove the latest index run finished.
- `GET /api/v0/status/index` returns the current Go-owned checkpoint summary.
- `GET /api/v0/index-status` is the legacy compatibility alias for the same
  Go-owned checkpoint summary.
- `GET /api/v0/repositories/{repo_id}/coverage` returns durable repository
  coverage rows for one repository.
- Run-scoped completeness routes such as `/api/v0/index-runs/{run_id}` are not
  ported yet on this branch. Keep that gap visible in parity tracking instead
  of assuming the repository coverage route is run-scoped.
- `GET /api/v0/ingesters/{ingester}` and `GET /api/v0/ingesters` report the
  hosted ingester's live status and progress, not graph completeness.
- Recovery operations (refinalize, replay) are owned by the Go ingester admin
  surface, not the Python API. See:
    - `POST http://<ingester>:8080/admin/refinalize` — re-enqueue active scope
      generations for re-projection.
    - `POST http://<ingester>:8080/admin/replay` — replay failed work items
      back to pending.
- `POST /api/v0/admin/reindex` persists an asynchronous ingester reindex
  request; the API process does not run the full reindex inline.
- `GET /api/v0/admin/shared-projection/tuning-report` returns the operator
  tuning report for shared-projection backlog behavior.

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
- documentation-oriented clients should resolve canonical graph identity first, then use `repo_id + relative_path` or `entity_id` for exact evidence reads.
- repository-oriented context, summary, story, stats, and file routes use canonical `repo_id` at the public boundary.

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

Entity context responses may also include semantic narrative fields when the
entity carries normalized semantic metadata:

- `semantic_summary`
- `semantic_profile`
- `story`

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

Repository story responses now expose a structured narrative contract. Workload
and service story responses stay narrative-first today. Use the deployment
trace route when you need the richer deployment-mapping contract.

Repository story responses are shaped around:

- `subject`
- `story`
- `story_sections`
- optional `semantic_overview`
- `deployment_overview`
- `gitops_overview`
- `documentation_overview`
- `support_overview`
- `coverage_summary`
- `limitations`
- `drilldowns`

When repository entities carry semantic signals, repository story responses
also:

- add a `semantics` entry into `story_sections`
- embed semantic coverage text into the top-level `story`
- expose aggregated semantic counts in `semantic_overview`

Workload and service story responses are still shaped around:

- `subject`
- `story`
- optional lightweight identifiers such as `subject`

Deployment-oriented trace responses are shaped around:

- `subject`
- `story`
- `story_sections`
- `deployment_overview`
- `gitops_overview`
- `controller_overview`
- `runtime_overview`
- `deployment_sources`
- `cloud_resources`
- `k8s_resources`
- `image_refs`
- `k8s_relationships`
- `controller_driven_paths`
- `delivery_paths`
- `deployment_fact_summary`
- `drilldowns`

The current deployment-oriented trace route is:

- `POST /api/v0/impact/trace-deployment-chain`

Deployment-oriented trace responses may also include:

- `deployment_facts`
- `deployment_fact_summary`

Use those when you need a stable, evidence-first contract instead of prose.

`deployment_fact_summary` reports:

- `mapping_mode`
- `overall_confidence`
- `overall_confidence_reason`
- `evidence_sources`
- fact types grouped by confidence
- `fact_thresholds`
- deployment-specific limitations such as `deployment_controller_unknown`

Mapping modes are intentionally controller-agnostic:

- `controller` for explicit controller evidence such as ArgoCD or Flux
- `iac` for explicit infrastructure-as-code evidence such as Terraform or CloudFormation
- `evidence_only` when delivery/runtime evidence exists but no trusted controller/IaC adapter was found
- `none` when no deployment evidence cleared the evidence thresholds and PCG can only report missing inputs

That lets the same story contract work across GitOps, IaC-driven, and controller-free estates without fabricating deployment tooling.

HTTP story routes stay canonical-ID based. If the caller starts with a fuzzy
name or alias, resolve first and then call the story route. Deployment traces
start from service names because they are the operator-facing entrypoint.

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

For documentation generation, use this HTTP flow:

1. call a story route first
2. if it is a repository story, read `story_sections`, `deployment_overview`, `gitops_overview`, `documentation_overview`, `support_overview`, `coverage_summary`, and `limitations`
3. if it is a workload or service story, pair it with `trace_deployment_chain` before you expect deployment overviews
4. only then call content routes for exact file or snippet evidence

For cross-repo documentation or support flows, phrase the caller intent the same
way you would through MCP: tell PCG to scan all related repositories,
deployment sources, and indexed documentation for the service or workload before asking
for the final narrative.

## Investigation API

Use this route when the caller wants PCG to plan the repo widening and evidence
search for them instead of manually chaining story, trace, and content calls.

### Investigate a service

`GET /api/v0/investigations/services/{service_name}`

Optional query params:

- `environment`
- `intent`
- `question`

The response is investigation-first rather than story-first. Key fields:

- `repositories_considered`
- `repositories_with_evidence`
- `evidence_families_found`
- `coverage_summary`
- `investigation_findings`
- `recommended_next_calls`

Coverage fields are meant to be truthful, not optimistic:

- `complete` means the indexed repository coverage explicitly reported complete
- `partial` means the indexed context or story limitations reported partial coverage
- `unknown` means PCG cannot currently prove complete or partial coverage from indexed evidence alone

This route is the HTTP inspection mode for operators:

- story/context routes remain the canonical-first truth surface
- investigation widens into evidence families and related repos on purpose
- inspection mode should explain gaps and widening decisions, not silently act like a second canonical graph

Use it for prompts like:

- "Explain the deployment flow for api-node-boats using PCG only."
- "Explain the network flow for api-node-boats using PCG only."
- "What depends on api-node-boats and what does it depend on?"

This route is designed for non-expert users who should not have to know which
deployment, GitOps, Terraform, workflow, or support repositories to inspect
next.

## Code API

Use these routes when you only need code relationships and do not need the full code-to-cloud graph.

- `POST /api/v0/code/search`
- `POST /api/v0/code/relationships`
- `POST /api/v0/code/dead-code`
- `POST /api/v0/code/complexity`

Public code-query requests use canonical `repo_id` whenever a repository scope
is part of the request. Results should be interpreted using `repo_id +
relative_path`, not absolute server-local paths.

`POST /api/v0/code/relationships` prefers `entity_id` when the caller already
has a canonical entity. It also accepts `name` for fallback lookup, plus
optional `direction` (`incoming` or `outgoing`) and `relationship_type`
filters when the caller only needs one edge class.

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
  "exclude_decorated_with": ["@route", "@app.route"]
}
```

`repo_id` is optional. When omitted, the Go API returns the first page of
dead-code candidates across indexed repositories and uses content metadata to
filter any decorator exclusions.

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
- documentation and runbook workflows should expect exact evidence to come from PostgreSQL-backed reads or search when available

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

Use these routes to inspect or control the deployed ingester runtime without reaching into Kubernetes directly.

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
