# Workload Graph Parity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the remaining MCP prompt gaps by materializing canonical workload/workload-instance nodes in the live graph, restoring path and change-surface traversal through those nodes, and making `content-entity:*` identifiers context-addressable.

**Architecture:** Stop synthesizing workloads independently in `resolve_entity`, `get_workload_context`, and impact queries. Instead, build canonical `Workload` and environment-scoped `WorkloadInstance` nodes during indexing from repository, ArgoCD, and deployment metadata, then make query surfaces read those nodes first with narrow fallbacks only for older graphs. Treat content entities as first-class context targets for the entities/context surface, but keep path/impact/traces restricted to traversable graph entity types.

**Tech Stack:** Python, Neo4j, pytest, FastAPI, MCP, Docker Compose, Postgres content store

---

## Chunk 1: Canonical Workload Materialization

### Task 1: Add red tests for live workload graph materialization

**Files:**
- Create: `tests/unit/tools/test_graph_builder_workloads.py`
- Modify: `tests/unit/query/test_entity_resolution.py`
- Modify: `tests/unit/query/test_workload_context.py`
- Modify: `tests/unit/query/test_change_surface.py`

- [ ] **Step 1: Write failing graph-builder tests**
Add tests that model the `api-node-search` shape and assert indexing materializes:
  - `Workload {id: "workload:api-node-search", kind: "service", repo_id: "repository:r_5c50d0d3"}`
  - `WorkloadInstance {id: "workload-instance:api-node-search:bg-qa", environment: "bg-qa", workload_id: "workload:api-node-search"}`
  - a deployment-source hop that can reach `repository:r_20871f7f` (`helm-charts`) from the workload or its environment-scoped instance.

- [ ] **Step 2: Write failing query tests**
Add focused red tests that prove the current live behavior is wrong:
  - `resolve_entity(..., query="workload-instance:api-node-search:bg-qa", exact=True)` should resolve the instance once the graph is correct.
  - `get_workload_context(..., workload_id="workload:api-node-search")` should not emit duplicate `default` instances from empty K8s namespaces.
  - `explain_dependency_path(..., source="workload:api-node-search", target="repository:r_20871f7f", environment="bg-qa")` should find a path.
  - `find_change_surface(..., target="workload:api-node-search")` should include the deployment-source repo instead of returning an empty impacted set.

- [ ] **Step 3: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/tools/test_graph_builder_workloads.py -q`
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_resolution.py tests/unit/query/test_workload_context.py tests/unit/query/test_change_surface.py -k "api_node_search or workload_instance or deployment_source" -q`
Expected: FAIL because workloads are still query-synthesized instead of graph-backed.

### Task 2: Materialize `Workload` and `WorkloadInstance` nodes during indexing

**Files:**
- Create: `src/platform_context_graph/tools/graph_builder_workloads.py`
- Modify: `src/platform_context_graph/tools/graph_builder.py`
- Modify: `src/platform_context_graph/tools/graph_builder_type_relationships.py`
- Modify: `src/platform_context_graph/tools/graph_builder_schema.py`
- Modify: `src/platform_context_graph/tools/cross_repo_linker.py`

- [ ] **Step 1: Add schema support**
Add Neo4j constraints and indexes for:
  - `Workload.id`
  - `WorkloadInstance.id`
  - optional helper indexes on `Workload.name`, `WorkloadInstance.environment`, and `Workload.repo_id` if needed for query performance.

- [ ] **Step 2: Implement workload derivation helper**
Create a dedicated builder helper that:
  - scans repositories plus linked ArgoCD/K8s deployment metadata after infra links exist
  - derives one logical workload per deployable app repo
  - derives environment-scoped workload instances from deployment metadata
  - prefers explicit deployment environment signals from Argo/ApplicationSet paths or overlay/config files over raw K8s namespaces
  - stores canonical IDs and `repo_id`/`workload_id` relationships needed by query surfaces.

- [ ] **Step 3: Persist canonical workload edges**
Materialize the minimum stable edge set needed for traversal parity:
  - `(:Repository)-[:DEFINES]->(:Workload)`
  - `(:WorkloadInstance)-[:INSTANCE_OF]->(:Workload)`
  - `(:WorkloadInstance)-[:DEPLOYMENT_SOURCE]->(:Repository)` when Argo/ApplicationSet evidence identifies the deployment repo for that environment.

- [ ] **Step 4: Wire the helper into indexing**
Invoke workload materialization after cross-repo infra linking in the main indexing flow so the derivation pass can reuse `SOURCES_FROM` and `DEPLOYS` edges instead of re-parsing raw files.

- [ ] **Step 5: Re-run the focused builder/query suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/tools/test_graph_builder_workloads.py -q`
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_resolution.py tests/unit/query/test_workload_context.py tests/unit/query/test_change_surface.py -k "api_node_search or workload_instance or deployment_source" -q`
Expected: PASS.

## Chunk 2: Query Surface Parity Over Canonical Workloads

### Task 3: Make entity resolution and workload context prefer graph-backed workload nodes

**Files:**
- Modify: `src/platform_context_graph/query/entity_resolution.py`
- Modify: `src/platform_context_graph/query/entity_resolution_database.py`
- Modify: `src/platform_context_graph/query/context/database.py`
- Modify: `tests/unit/query/test_entity_resolution.py`
- Modify: `tests/unit/query/test_workload_context.py`
- Modify: `tests/integration/api/test_entities_api.py`
- Modify: `tests/integration/mcp/test_mcp_server.py`

- [ ] **Step 1: Write the failing parity tests**
Add or extend tests to require:
  - live-db `resolve_entity` prefers real `Workload`/`WorkloadInstance` rows over query-only synthetic rows
  - exact canonical workload/workload-instance IDs resolve successfully
  - `get_workload_context` and `get_service_context` surface the real environment-scoped instance (`bg-qa`) without duplicating placeholder instances
  - MCP wrappers pass the corrected workload results through unchanged.

- [ ] **Step 2: Run the red scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_resolution.py tests/unit/query/test_workload_context.py tests/integration/api/test_entities_api.py tests/integration/mcp/test_mcp_server.py -q`
Expected: FAIL on at least the new workload-instance and graph-backed-context assertions before implementation.

- [ ] **Step 3: Implement graph-first reads with compatibility fallback**
Update query code so it:
  - reads persisted `Workload` and `WorkloadInstance` nodes first
  - keeps the current synthetic fallback only for older graphs that have not been reindexed yet
  - treats environment as deployment environment, not a blind alias for K8s namespace
  - deduplicates returned instances and preserves canonical repo metadata.

- [ ] **Step 4: Re-run the parity suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_resolution.py tests/unit/query/test_workload_context.py tests/integration/api/test_entities_api.py tests/integration/mcp/test_mcp_server.py -q`
Expected: PASS.

### Task 4: Restore impact/path/change-surface traversal through workloads

**Files:**
- Modify: `src/platform_context_graph/query/impact/database.py`
- Modify: `src/platform_context_graph/query/impact/store.py`
- Modify: `src/platform_context_graph/query/impact/common.py`
- Modify: `tests/unit/query/test_change_surface.py`
- Modify: `tests/integration/api/test_paths_api.py`
- Modify: `tests/integration/api/test_impact_api.py`

- [ ] **Step 1: Add failing traversal tests**
Cover these behaviors explicitly:
  - `find_change_surface(target="workload:api-node-search")` includes the `helm-charts` repository via `DEPLOYMENT_SOURCE`
  - `explain_dependency_path(source="workload:api-node-search", target="repository:r_20871f7f", environment="bg-qa")` returns a non-empty path
  - `get_entity_context("workload-instance:api-node-search:bg-qa")` stays consistent with the workload-context response
  - no traversal path is synthesized through non-canonical or null endpoints.

- [ ] **Step 2: Run the red traversal scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_change_surface.py tests/integration/api/test_paths_api.py tests/integration/api/test_impact_api.py -q`
Expected: FAIL on the new workload traversal expectations before implementation.

- [ ] **Step 3: Implement the minimal traversal fix**
Only change what is required for workload parity:
  - fetch persisted workload/workload-instance rows as first-class entities
  - let `_GraphStore.from_source` expand through `repo_id`, `workload_id`, and persisted workload edges
  - keep existing inferred `DEFINES` behavior only as a backward-compatibility fallback for older graphs.

- [ ] **Step 4: Re-run the traversal scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_change_surface.py tests/integration/api/test_paths_api.py tests/integration/api/test_impact_api.py -q`
Expected: PASS.

## Chunk 3: Content Entity Context Support

### Task 5: Make `content-entity:*` IDs context-addressable without polluting path/impact routes

**Files:**
- Modify: `src/platform_context_graph/domain/entities.py`
- Modify: `src/platform_context_graph/api/routers/_shared.py`
- Modify: `src/platform_context_graph/api/routers/entities.py`
- Modify: `src/platform_context_graph/query/context/__init__.py`
- Create: `src/platform_context_graph/query/context/content_entity.py`
- Modify: `src/platform_context_graph/query/content.py`
- Modify: `tests/integration/api/test_entities_api.py`
- Modify: `tests/integration/api/test_content_api.py`
- Modify: `tests/unit/query/test_entity_context.py`
- Modify: `tests/integration/mcp/test_mcp_server.py`

- [ ] **Step 1: Add failing entity-context tests**
Require:
  - `GET /api/v0/entities/content-entity:.../context` returns `200`
  - MCP `get_entity_context(entity_id="content-entity:...")` returns content-backed metadata instead of a tool error
  - `content-entity:*` still remains invalid for path/impact/traces routes unless explicit traversal support is added later.

- [ ] **Step 2: Run the red scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_context.py tests/integration/api/test_entities_api.py tests/integration/api/test_content_api.py tests/integration/mcp/test_mcp_server.py -k "content_entity or content-entity" -q`
Expected: FAIL because generic entity context does not yet support content entity IDs.

- [ ] **Step 3: Implement content-entity context dispatch**
Add a narrow content-entity context branch that:
  - treats content entities as a real entity type for entity-context responses
  - resolves content metadata through the content service
  - returns the owning repository plus file-relative location in the context payload
  - leaves traces/path/impact validation unchanged or explicitly rejects `content-entity:*` there with a clear problem response.

- [ ] **Step 4: Re-run the content-context scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_context.py tests/integration/api/test_entities_api.py tests/integration/api/test_content_api.py tests/integration/mcp/test_mcp_server.py -k "content_entity or content-entity" -q`
Expected: PASS.

## Chunk 4: Runtime Dependency Edges and Real Prompt Regression

### Task 6: Promote runtime-declared service dependencies into graph edges

**Files:**
- Create: `src/platform_context_graph/tools/languages/runtime_dependencies.py`
- Modify: `src/platform_context_graph/tools/graph_builder_persistence.py`
- Modify: `src/platform_context_graph/tools/graph_builder_workloads.py`
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Modify: `tests/unit/tools/test_graph_builder_workloads.py`
- Modify: `tests/unit/query/test_workload_context.py`

- [ ] **Step 1: Add failing dependency-edge tests**
Add tests around the `api-node-search.ts` startup shape so declared runtime services like `api-node-forex` become graph edges that workload/repository context can surface.

- [ ] **Step 2: Run the red dependency scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/tools/test_graph_builder_workloads.py tests/unit/query/test_workload_context.py -k "api_node_forex or dependency" -q`
Expected: FAIL because those edges are not currently materialized.

- [ ] **Step 3: Implement minimal dependency extraction**
Extract dependency strings from supported startup patterns such as `api.start({ services: [...] })`, then connect them to canonical repositories/workloads when they resolve cleanly. Keep cloud-style dependencies like `opensearch/products` or `elasticache` as unresolved evidence until the graph has first-class cloud endpoints for them.

- [ ] **Step 4: Re-run the dependency scope**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/tools/test_graph_builder_workloads.py tests/unit/query/test_workload_context.py -k "api_node_forex or dependency" -q`
Expected: PASS.

### Task 7: Rebuild locally and verify the real Codex prompt path against Mobius

**Files:**
- Modify: any files from prior tasks
- Test: local Docker Compose stack and real Codex MCP client

- [ ] **Step 1: Run the broader focused regression suite**
Run:
  - `PYTHONPATH=src uv run pytest tests/unit/query/test_entity_resolution.py tests/unit/query/test_workload_context.py tests/unit/query/test_change_surface.py tests/unit/query/test_entity_context.py tests/unit/tools/test_graph_builder_workloads.py tests/unit/tools/test_code_finder.py tests/integration/api/test_entities_api.py tests/integration/api/test_paths_api.py tests/integration/api/test_impact_api.py tests/integration/api/test_content_api.py tests/integration/mcp/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 2: Run repository guardrails**
Run:
  - `python3 scripts/check_python_file_lengths.py --max-lines 500`
  - `python3 scripts/check_python_docstrings.py`
Expected: PASS.

- [ ] **Step 3: Rebuild the local stack against Mobius**
Run:
  - `PCG_FILESYSTEM_HOST_ROOT=/Users/allen/repos/mobius docker-compose up -d --build platform-context-graph repo-sync`
  - `docker-compose ps`
  - `curl -fsS http://localhost:8080/health`
Expected: healthy services.

- [ ] **Step 4: Verify live API behavior**
Run:
  - `curl -fsS -X POST http://localhost:8080/api/v0/entities/resolve -H 'content-type: application/json' -d '{"query":"api-node-search","types":["workload"],"limit":5}'`
  - `curl -fsS -X POST http://localhost:8080/api/v0/paths/explain -H 'content-type: application/json' -d '{"source":"workload:api-node-search","target":"repository:r_20871f7f","environment":"bg-qa"}'`
  - `curl -fsS -X POST http://localhost:8080/api/v0/impact/change-surface -H 'content-type: application/json' -d '{"target":"workload:api-node-search"}'`
  - `curl -fsS http://localhost:8080/api/v0/entities/content-entity:e_0a5bf8636d63/context`
Expected: all return successful, non-empty workload-aware responses.

- [ ] **Step 5: Verify the real Codex client path**
Run:
  - `codex exec --skip-git-repo-check --sandbox read-only --json "Use the platform-context-graph MCP server to explain the workload api-node-search and trace the end-to-end flow from code to infra. Ground the answer in MCP tool results and explicitly label any remaining inferred links."`
Expected:
  - resolves `workload:api-node-search` without falling back to repo-only identity
  - finds a non-empty path from workload to `helm-charts`
  - does not error on package-style code search queries
  - can inspect `content-entity:*` IDs without MCP tool failure
  - still labels genuinely unmodeled cloud-resource links as inferred.

- [ ] **Step 6: Do not commit until the full local gate is green**
The user’s acceptance rule still applies: no commit until the build is clean and the end-to-end local Mobius-backed prompt path is verified.
