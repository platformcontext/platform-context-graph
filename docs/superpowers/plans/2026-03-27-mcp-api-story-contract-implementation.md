# MCP/API Story And Programming Prompt Contract Implementation Plan

## Scope

Implement the two-lane prompt contract described in
[../specs/2026-03-27-mcp-api-story-contract-design.md](../specs/2026-03-27-mcp-api-story-contract-design.md)
without reopening the shared-query umbrella in
[../specs/2026-03-19-query-model-api-design.md](../specs/2026-03-19-query-model-api-design.md).

This plan assumes the shared query layer remains the architectural base and that
the work here is about user-facing contract shape, transport parity, prompt
acceptance suites, and evidence safety.

## Worker Split

### Worker 1: PRD/spec and docs alignment

- rewrite the story/programming PRD
- write this implementation plan
- align public docs so they describe the new story tools and HTTP story routes

### Worker 2: Story lane

- add story-oriented query helpers
- add MCP story tools for repository, workload, and service narratives
- add HTTP story endpoints for repositories, workloads, and services
- add OpenAPI examples and contract tests

### Worker 3: Programming lane

- normalize public programming contracts around canonical `repo_id`
- align MCP and HTTP defaults for code search
- fix `module_deps`
- preserve repo-relative drill-down behavior for code results

### Worker 4: Acceptance harness

- create the shared prompt corpus
- add MCP and HTTP transport adapters
- add integration coverage for the 20 story prompts and 16 programming prompts
- keep a smaller Docker-backed e2e subset for both lanes

### Worker 5: Security review

- review new story surfaces for evidence leakage and path portability
- ensure new public surfaces do not normalize raw Cypher or server-local
  filesystem usage
- verify auth and runtime-role assumptions remain intact

## Required Skills

- `brainstorming` for the already-completed design direction
- `writing-plans` for this implementation document
- `python-engineering` for query, API, MCP, and test changes
- `security-repo-auditor` for public-surface and evidence-exposure review
- `dispatching-parallel-agents` / subagent-driven execution for parallel slices
- `verification-before-completion` before claiming the branch is done

## Phase 1: Shared Contract Inputs

- create one shared prompt corpus for:
  - 20 story prompts
  - 16 programming prompts
- encode both MCP and HTTP expectations in the same scenario table
- make the scenario table durable and importable by multiple integration suites

Files:

- `tests/integration/prompt_contract_cases.py`

## Phase 2: Story Lane

### Query and domain layer

- add a shared story response builder that returns:
  - `subject`
  - `story`
  - `story_sections`
  - `deployment_overview` / `code_overview`
  - `evidence`
  - `limitations`
  - `coverage`
  - `drilldowns`
- ensure repository story subjects do not expose server-local checkout paths as
  part of the normal story contract

Files:

- `src/platform_context_graph/query/story.py`
- `src/platform_context_graph/domain/responses.py`
- `tests/unit/query/test_story.py`

### MCP surfaces

- add `get_repo_story`
- add `get_workload_story`
- add `get_service_story`
- keep lower-level context tools as drill-down surfaces, not replacements

Files:

- `src/platform_context_graph/mcp/query_tools.py`
- `src/platform_context_graph/mcp/tools/ecosystem.py`
- `src/platform_context_graph/mcp/tools/context.py`
- `src/platform_context_graph/mcp/tool_dispatch.py`
- `src/platform_context_graph/mcp/tool_registry.py`

### HTTP surfaces

- add `GET /api/v0/repositories/{repo_id}/story`
- add `GET /api/v0/workloads/{workload_id}/story`
- add `GET /api/v0/services/{workload_id}/story`
- keep HTTP canonical-ID based
- document `resolve` first for fuzzy-name flows

Files:

- `src/platform_context_graph/api/routers/repositories.py`
- `src/platform_context_graph/api/routers/workloads.py`
- `src/platform_context_graph/api/routers/services.py`
- `src/platform_context_graph/api/app_openapi.py`
- `tests/integration/api/test_story_api.py`
- `tests/integration/api/test_openapi_contract.py`

## Phase 3: Programming Lane

### Public contract normalization

- use canonical `repo_id` terminology across public code-query surfaces
- keep internal legacy `repo_path` bridging private to the query layer
- align dead-code scoping with the same public repository contract

Files:

- `src/platform_context_graph/query/code.py`
- `src/platform_context_graph/api/routers/code.py`
- `src/platform_context_graph/mcp/server.py`
- `src/platform_context_graph/mcp/tools/codebase.py`

### Behavior parity

- keep MCP and HTTP search defaults aligned
- preserve repo-relative drill-down shape
- normalize `module_deps`
- preserve `workspace`/`ecosystem` behavior intentionally and document it

Files:

- `src/platform_context_graph/tools/code_finder_dispatch.py`
- `tests/unit/query/test_code_queries.py`
- `tests/unit/tools/test_code_finder.py`
- `tests/unit/mcp/test_cypher_schema_docs.py`
- `tests/integration/api/test_code_api.py`
- `tests/integration/mcp/test_mcp_server.py`

## Phase 4: Acceptance Harness

### Integration

- add MCP prompt-contract suite powered by the shared scenario table
- add HTTP prompt-contract suite powered by the same scenario table
- assert structure, portability, canonical identity, and drill-down readiness

Files:

- `tests/integration/mcp/test_prompt_contract_mcp.py`
- `tests/integration/api/test_prompt_contract_api.py`

### Docs and smoke tests

- update MCP guide to prefer story tools for story-shaped questions
- update MCP reference to list the story tools and portability guardrails
- update HTTP reference to document the new story endpoints and `resolve`-first
  guidance

Files:

- `docs/docs/guides/mcp-guide.md`
- `docs/docs/reference/mcp-reference.md`
- `docs/docs/reference/http-api.md`
- `tests/integration/docs/test_docs_smoke.py`

## Phase 5: Security Review

- review story responses for path leakage
- ensure evidence entries do not normalize server-local filesystem usage
- ensure story routes remain protected by the same HTTP auth contract as the
  rest of the query API
- ensure new MCP story tools stay read-only and compatible with runtime-role
  filtering

## Verification

Run focused verification before merge:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/query/test_story.py \
  tests/unit/query/test_code_queries.py \
  tests/unit/tools/test_code_finder.py \
  tests/unit/mcp/test_cypher_schema_docs.py \
  tests/integration/api/test_story_api.py \
  tests/integration/api/test_code_api.py \
  tests/integration/api/test_openapi_contract.py \
  tests/integration/api/test_prompt_contract_api.py \
  tests/integration/mcp/test_mcp_server.py \
  tests/integration/mcp/test_repository_runtime_context.py \
  tests/integration/mcp/test_prompt_contract_mcp.py \
  tests/integration/docs/test_docs_smoke.py
```

Run the Docker-backed flagship subset after the integration contract is green:

```bash
env PCG_E2E_PYTEST_WORKERS=4 ./tests/run_tests.sh e2e
```

## Completion Criteria

- PRD and implementation plan are present and aligned
- story surfaces exist on both MCP and HTTP
- programming surfaces are normalized around public `repo_id`
- the shared prompt corpus powers both MCP and HTTP integration suites
- docs match the implemented public contract
- security review finds no remaining high/medium evidence-exposure issues in the
  new story surfaces
