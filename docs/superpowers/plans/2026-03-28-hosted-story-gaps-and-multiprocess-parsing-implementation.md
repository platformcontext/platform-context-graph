# Hosted Story Gaps And Multiprocess Parsing Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the remaining hosted MCP/API story-completeness gaps while adding a feature-flagged multiprocess parse engine that improves CPU-bound indexing throughput without changing graph correctness.

**Architecture:** Keep this as two coordinated workstreams. Workstream A extends the shared query and enrichment layer so hosted investigations can stay inside PCG surfaces. Workstream B preserves the single-writer coordinator and bounded snapshot queue while swapping only the parse execution engine behind a flag.

**Tech Stack:** Python 3.12, FastAPI, MCP server mixins, Neo4j-backed query layer, asyncio coordinator pipeline, tree-sitter parsers, pytest, docker-backed e2e verification.

---

## File Map

### Workstream A: Hosted story and tool gaps

- Modify: `src/platform_context_graph/query/repositories/__init__.py`
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment_consumers.py`
- Modify: `src/platform_context_graph/query/context/__init__.py`
- Modify: `src/platform_context_graph/query/infra.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem_support.py`
- Modify: `src/platform_context_graph/mcp/query_tools.py`
- Modify: `src/platform_context_graph/mcp/tools/ecosystem.py`
- Modify: `src/platform_context_graph/mcp/tools/runtime.py`
- Test: `tests/unit/query/test_content_queries.py`
- Test: `tests/unit/mcp/test_runtime_tools.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`
- Test: `tests/integration/api/test_story_api.py`
- Test: `tests/e2e/test_prompt_contract_user_journeys.py`

### Workstream B: Multiprocess parsing

- Create: `src/platform_context_graph/tools/parse_worker.py`
- Modify: `src/platform_context_graph/tools/graph_builder_indexing_execution.py`
- Modify: `src/platform_context_graph/tools/graph_builder_parsers.py`
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Modify: `src/platform_context_graph/indexing/coordinator_pipeline.py`
- Modify: `src/platform_context_graph/tools/graph_builder.py`
- Modify: `src/platform_context_graph/cli/config_manager.py`
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Test: `tests/unit/indexing/test_coordinator_pipeline.py`
- Test: `tests/unit/tools/test_graph_builder_parsers.py`
- Create/Test: `tests/unit/tools/test_parse_worker.py`
- Create/Test: `tests/integration/indexing/test_parse_engine_equivalence.py`
- Create: `scripts/benchmark_parse_engine.py`

## Chunk 1: Hosted Gap Fact Check And Spec Alignment

**Files:**
- Modify: `docs/superpowers/specs/2026-03-28-hosted-story-gaps-and-multiprocess-parsing-design.md`
- Modify: `docs/superpowers/plans/2026-03-28-hosted-story-gaps-and-multiprocess-parsing-implementation.md`

- [ ] **Step 1: Confirm which hosted-gap findings are already fixed on this branch**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/query/test_content_queries.py \
  tests/unit/mcp/test_runtime_tools.py \
  tests/unit/handlers/test_repo_context.py -k "file_content or index_status or blast_radius or trace_deployment_chain"
```

Expected: green targeted tests proving which gaps are already closed.

- [ ] **Step 2: Update spec/plan language so stale findings become verification notes, not duplicate work**

Capture:

- `get_file_content` repo-name support as already landed
- `get_index_status` name resolution as already landed
- `find_blast_radius` null placeholder as fixed, richer consumer evidence still open
- `trace_deployment_chain` overmatch as reduced, shaping controls still open

- [ ] **Step 3: Commit the doc-only alignment**

```bash
git add docs/superpowers/specs/2026-03-28-hosted-story-gaps-and-multiprocess-parsing-design.md \
  docs/superpowers/plans/2026-03-28-hosted-story-gaps-and-multiprocess-parsing-implementation.md
git commit -m "docs: align hosted gap and parse design"
```

## Chunk 2: Repository And Service Context Enrichment

**Files:**
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment.py`
- Modify: `src/platform_context_graph/query/repositories/content_enrichment_consumers.py`
- Modify: `src/platform_context_graph/query/repositories/__init__.py`
- Modify: `src/platform_context_graph/query/context/__init__.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/integration/api/test_story_api.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`

- [ ] **Step 1: Write failing tests for missing hosted fields**

Add cases for:

- repository `platforms`
- repository `environments`
- repository `deploys_from`
- service `cloud_resources`
- service `shared_resources`
- service `dependencies`
- service `entrypoints`

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/api/test_story_api.py \
  tests/integration/mcp/test_repository_runtime_context.py -k "platforms or environments or cloud_resources or shared_resources or entrypoints"
```

Expected: failures showing the current empty or under-shaped fields.

- [ ] **Step 3: Extend repository enrichment with richer deployment/environment facts**

Implement minimal code to:

- derive structured environments from overlays and config evidence
- carry `deploys_from` and related source evidence into the story/context layer
- keep `limitations` and `coverage` truthful when finalization is incomplete

- [ ] **Step 4: Extend service/workload context with structured resource and dependency extraction**

Implement minimal code to extract:

- gateway refs
- image/ECR references
- IAM/SSM resource patterns
- shared cache or service endpoint hints

- [ ] **Step 5: Re-run focused tests**

Run the command from step 2.

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/platform_context_graph/query/repositories/__init__.py \
  src/platform_context_graph/query/repositories/context_data.py \
  src/platform_context_graph/query/repositories/content_enrichment.py \
  src/platform_context_graph/query/repositories/content_enrichment_consumers.py \
  src/platform_context_graph/query/context/__init__.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/api/test_story_api.py \
  tests/integration/mcp/test_repository_runtime_context.py
git commit -m "feat: enrich hosted repository and service context"
```

## Chunk 3: Infra Classification And Blast Radius Quality

**Files:**
- Modify: `src/platform_context_graph/query/infra.py`
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/integration/mcp/test_repository_runtime_context.py`

- [ ] **Step 1: Write failing tests for ApplicationSet and Crossplane claim classification**

Cover:

- `find_infra_resources(..., category="argocd")` returns `ApplicationSet`
- `find_infra_resources(..., category="crossplane")` returns claim instances

- [ ] **Step 2: Write failing tests for richer blast-radius results**

Cover:

- no null placeholder rows
- concrete repo identities
- truthful metadata when tier/risk are absent
- fallback augmentation from repository consumer evidence

- [ ] **Step 3: Run tests to verify failure**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py -k "argocd or crossplane or blast_radius"
```

Expected: targeted failures.

- [ ] **Step 4: Implement minimal classification and blast-radius fixes**

Preserve additive response shape. Add notes when metadata is inferred or absent.

- [ ] **Step 5: Re-run focused tests**

Run the command from step 3.

Expected: green.

- [ ] **Step 6: Commit**

```bash
git add src/platform_context_graph/query/infra.py \
  src/platform_context_graph/mcp/tools/handlers/ecosystem.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py
git commit -m "feat: improve infra classification and blast radius"
```

## Chunk 4: Deployment Trace Shaping

**Files:**
- Modify: `src/platform_context_graph/mcp/tools/handlers/ecosystem_support.py`
- Modify: `src/platform_context_graph/mcp/query_tools.py`
- Modify: `src/platform_context_graph/mcp/tools/ecosystem.py`
- Test: `tests/unit/handlers/test_repo_context.py`
- Test: `tests/e2e/test_prompt_contract_user_journeys.py`

- [ ] **Step 1: Write failing tests for direct-only and bounded deployment tracing**

Add cases for:

- direct-only trace
- bounded depth
- truncation metadata or note when related branches are omitted

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/handlers/test_repo_context.py \
  tests/e2e/test_prompt_contract_user_journeys.py -k "trace_deployment_chain or deployment story"
```

Expected: targeted failures or missing-field assertions.

- [ ] **Step 3: Implement shaping controls without breaking current callers**

Add optional parameters and preserve legacy default behavior as closely as
possible while tightening the default hosted story path.

- [ ] **Step 4: Re-run focused tests**

Run the command from step 2.

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/mcp/tools/handlers/ecosystem_support.py \
  src/platform_context_graph/mcp/query_tools.py \
  src/platform_context_graph/mcp/tools/ecosystem.py \
  tests/unit/handlers/test_repo_context.py \
  tests/e2e/test_prompt_contract_user_journeys.py
git commit -m "feat: add focused deployment trace controls"
```

## Chunk 5: Multiprocess Parse Engine And Bounded Queue

**Files:**
- Create: `src/platform_context_graph/tools/parse_worker.py`
- Modify: `src/platform_context_graph/tools/graph_builder_parsers.py`
- Modify: `src/platform_context_graph/tools/graph_builder_indexing_execution.py`
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Modify: `src/platform_context_graph/indexing/coordinator_pipeline.py`
- Modify: `src/platform_context_graph/tools/graph_builder.py`
- Modify: `src/platform_context_graph/cli/config_manager.py`
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Test: `tests/unit/tools/test_parse_worker.py`
- Test: `tests/unit/indexing/test_coordinator_pipeline.py`

- [ ] **Step 1: Write failing tests for engine selection and worker initialization**

Cover:

- process engine config selection
- worker init builds parser registry once per worker
- parse snapshots enter a bounded queue and commit in order
- standalone parse entrypoint returns the same payload shape as current parsing

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/tools/test_parse_worker.py \
  tests/unit/indexing/test_coordinator_pipeline.py -k "parse engine or process pool or worker"
```

Expected: failures because the new engine path does not exist yet.

- [ ] **Step 3: Add the worker module and feature-flagged engine selection**

Implement:

- `PCG_PARSE_EXECUTION_ENGINE`
- process worker initializer
- standalone parse entrypoint
- coordinator wiring for a process pool
- bounded queue/backpressure in the coordinator remains the single-writer handoff

Do not remove the thread engine.

- [ ] **Step 4: Re-run focused tests**

Run the command from step 2.

Expected: green.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/tools/parse_worker.py \
  src/platform_context_graph/tools/graph_builder_parsers.py \
  src/platform_context_graph/tools/graph_builder_indexing_execution.py \
  src/platform_context_graph/indexing/coordinator.py \
  src/platform_context_graph/indexing/coordinator_pipeline.py \
  src/platform_context_graph/tools/graph_builder.py \
  src/platform_context_graph/cli/config_manager.py \
  src/platform_context_graph/cli/helpers/indexing.py \
  tests/unit/tools/test_parse_worker.py \
  tests/unit/indexing/test_coordinator_pipeline.py
git commit -m "feat: add process-backed parse engine"
```

## Chunk 6: Parse Equivalence And Benchmarking

**Files:**
- Create: `tests/integration/indexing/test_parse_engine_equivalence.py`
- Create: `scripts/benchmark_parse_engine.py`
- Modify: `tests/e2e/test_prompt_contract_user_journeys.py`

- [ ] **Step 1: Write failing equivalence tests**

Add tests that parse the same representative fixture repo under:

- `thread` engine
- `process` engine

Assert equivalent parse payloads and downstream snapshot semantics.

- [ ] **Step 2: Add a benchmark harness**

Create a script that records:

- repo name
- engine
- worker count
- queue depth
- elapsed parse time
- elapsed pre-scan time
- output counts

The script should report data but not assert hard thresholds.

- [ ] **Step 3: Run focused equivalence tests**

Run:

```bash
PYTHONPATH=src:. uv run pytest -q tests/integration/indexing/test_parse_engine_equivalence.py
```

Expected: green equivalence checks.

- [ ] **Step 4: Capture at least one benchmark run**

Run:

```bash
PYTHONPATH=src:. uv run python scripts/benchmark_parse_engine.py --repo tests/fixtures/ecosystems/python_comprehensive --engines thread,process
```

Expected: printed timing report and no correctness mismatches.

- [ ] **Step 5: Commit**

```bash
git add tests/integration/indexing/test_parse_engine_equivalence.py \
  scripts/benchmark_parse_engine.py \
  tests/e2e/test_prompt_contract_user_journeys.py
git commit -m "test: add parse engine equivalence and benchmark harness"
```

## Chunk 7: Full Verification

**Files:**
- Modify: none unless verification exposes bugs

- [ ] **Step 1: Run focused hosted-query verification**

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/query/test_content_queries.py \
  tests/unit/mcp/test_runtime_tools.py \
  tests/unit/handlers/test_repo_context.py \
  tests/integration/mcp/test_repository_runtime_context.py \
  tests/integration/api/test_story_api.py
```

Expected: all green.

- [ ] **Step 2: Run multiprocess engine verification**

```bash
PYTHONPATH=src:. uv run pytest -q \
  tests/unit/tools/test_parse_worker.py \
  tests/unit/indexing/test_coordinator_pipeline.py \
  tests/integration/indexing/test_parse_engine_equivalence.py
```

Expected: all green.

- [ ] **Step 3: Run docker-backed e2e verification**

```bash
DATABASE_TYPE=neo4j \
NEO4J_URI=bolt://localhost:7687 \
NEO4J_USERNAME=neo4j \
NEO4J_PASSWORD=testpassword \
PYTHONPATH=src:. uv run python scripts/seed_e2e_graph.py

DATABASE_TYPE=neo4j \
NEO4J_URI=bolt://localhost:7687 \
NEO4J_USERNAME=neo4j \
NEO4J_PASSWORD=testpassword \
PCG_E2E_PYTEST_WORKERS=4 \
./tests/run_tests.sh e2e
```

Expected: green wrapper run with the story/programming prompt journeys included.

- [ ] **Step 4: Commit final verification-only or follow-up fixes if needed**

```bash
git status --short
```

If clean, no commit needed. If verification required fixes, commit them with a
verification-specific message.

## Plan Complete

Plan complete and saved to `docs/superpowers/plans/2026-03-28-hosted-story-gaps-and-multiprocess-parsing-implementation.md`. Ready to execute.
