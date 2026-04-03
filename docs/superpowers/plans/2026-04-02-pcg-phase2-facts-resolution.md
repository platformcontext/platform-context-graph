# PCG Phase 2 Facts And Resolution Engine Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Switch the Git indexing path from direct graph writes to a facts-first pipeline backed by Postgres and a new Resolution Engine runtime.

**Architecture:** Add typed fact contracts, a Postgres fact store, and a Postgres work queue in front of a standalone Resolution Engine service. Emit facts from the Git repository snapshot seam, then project repository, file, entity, call, inheritance, workload, and platform graph state from facts until the old direct path can be removed.

**Tech Stack:** Python, pytest, Postgres, existing PCG Git collector/runtime/indexing stack, Neo4j graph projection, ripgrep

---

## Chunk 1: Facts Foundation

### Task 1: Create fact models and identifiers

**Files:**
- Create: `src/platform_context_graph/facts/models/__init__.py`
- Create: `src/platform_context_graph/facts/models/base.py`
- Create: `src/platform_context_graph/facts/models/git.py`
- Create: `src/platform_context_graph/facts/provenance.py`
- Test: `tests/unit/facts/test_fact_models.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- stable fact type names
- required provenance fields
- deterministic fact ids for the same source input

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_models.py -q`
Expected: FAIL because the facts model modules do not exist yet.

- [ ] **Step 3: Implement the minimal fact model layer**

Add:
- a shared base fact model
- Git-specific fact models for repository, file, import, parsed entity, workload input, and platform input
- helper(s) for deterministic ids and provenance normalization

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_models.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts tests/unit/facts/test_fact_models.py
git commit -m "feat: add phase2 fact models"
```

### Task 2: Add Postgres fact storage contracts

**Files:**
- Create: `src/platform_context_graph/facts/storage/__init__.py`
- Create: `src/platform_context_graph/facts/storage/models.py`
- Create: `src/platform_context_graph/facts/storage/postgres.py`
- Create: `src/platform_context_graph/facts/storage/schema.py`
- Test: `tests/unit/facts/test_fact_store_postgres.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- storing a batch of fact records
- loading fact records by repository and run
- idempotent write behavior on repeated inserts

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_store_postgres.py -q`
Expected: FAIL because the storage package does not exist yet.

- [ ] **Step 3: Implement the minimal Postgres fact store**

Add:
- fact run row model
- fact record row model
- schema bootstrap helper
- batch insert and read APIs

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_store_postgres.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts tests/unit/facts/test_fact_store_postgres.py
git commit -m "feat: add postgres-backed fact store"
```

## Chunk 2: Work Queue And Resolution Runtime

### Task 3: Add Postgres work queue / outbox

**Files:**
- Create: `src/platform_context_graph/facts/work_queue/__init__.py`
- Create: `src/platform_context_graph/facts/work_queue/models.py`
- Create: `src/platform_context_graph/facts/work_queue/postgres.py`
- Create: `src/platform_context_graph/facts/work_queue/schema.py`
- Test: `tests/unit/facts/test_fact_work_queue.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- enqueueing work items
- claiming a lease
- retry count increment
- terminal failure marking

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue.py -q`
Expected: FAIL because the work queue package does not exist yet.

- [ ] **Step 3: Implement the Postgres queue**

Add:
- work item row model
- queue schema bootstrap
- enqueue/claim/complete/fail operations

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts tests/unit/facts/test_fact_work_queue.py
git commit -m "feat: add phase2 fact work queue"
```

### Task 4: Implement a real Resolution Engine runtime

**Files:**
- Create: `src/platform_context_graph/resolution/orchestration/__init__.py`
- Create: `src/platform_context_graph/resolution/orchestration/engine.py`
- Create: `src/platform_context_graph/resolution/orchestration/runtime.py`
- Modify: `src/platform_context_graph/app/service_entrypoints.py`
- Test: `tests/unit/resolution/test_resolution_engine_entrypoint.py`
- Test: `tests/unit/resolution/test_resolution_engine_runtime.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- `resolution-engine` service role resolves to a real implementation
- runtime claims a work item and dispatches to a projection handler

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_engine_entrypoint.py tests/unit/resolution/test_resolution_engine_runtime.py -q`
Expected: FAIL because the runtime does not exist yet.

- [ ] **Step 3: Implement the Resolution Engine shell**

Add:
- a worker loop
- work-item claim/complete/fail behavior
- a thin orchestration layer that can call projection stages

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_engine_entrypoint.py tests/unit/resolution/test_resolution_engine_runtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/app src/platform_context_graph/resolution tests/unit/resolution
git commit -m "feat: add resolution engine runtime"
```

## Chunk 3: Git Fact Emission

### Task 5: Emit facts from the repository snapshot seam

**Files:**
- Create: `src/platform_context_graph/facts/emission/__init__.py`
- Create: `src/platform_context_graph/facts/emission/git_snapshot.py`
- Modify: `src/platform_context_graph/indexing/coordinator_pipeline.py`
- Modify: `src/platform_context_graph/collectors/git/parse_execution.py`
- Test: `tests/unit/facts/test_git_snapshot_fact_emission.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- converting a `RepositoryParseSnapshot` into fact records
- enqueueing one resolution work item per repository snapshot

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_git_snapshot_fact_emission.py -q`
Expected: FAIL because the fact emission module does not exist yet.

- [ ] **Step 3: Implement snapshot-to-facts emission**

Add:
- conversion from repository snapshot to fact records
- write-to-store + enqueue behavior at the coordinator snapshot seam
- minimal run/snapshot identifiers

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_git_snapshot_fact_emission.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts src/platform_context_graph/indexing src/platform_context_graph/collectors/git tests/unit/facts/test_git_snapshot_fact_emission.py
git commit -m "feat: emit git facts from repository snapshots"
```

## Chunk 4: Graph Projection From Facts

### Task 6: Project repository, file, and parsed entity graph state from facts

**Files:**
- Create: `src/platform_context_graph/resolution/projection/__init__.py`
- Create: `src/platform_context_graph/resolution/projection/repositories.py`
- Create: `src/platform_context_graph/resolution/projection/files.py`
- Create: `src/platform_context_graph/resolution/projection/entities.py`
- Test: `tests/unit/resolution/test_fact_projection_repositories.py`
- Test: `tests/unit/resolution/test_fact_projection_entities.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- repository graph projection from repository facts
- file/entity graph projection from file and parsed entity facts

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_repositories.py tests/unit/resolution/test_fact_projection_entities.py -q`
Expected: FAIL because the projection modules do not exist yet.

- [ ] **Step 3: Implement minimal projection handlers**

Reuse the canonical graph persistence package where possible instead of
re-implementing Cypher assembly.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_repositories.py tests/unit/resolution/test_fact_projection_entities.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution tests/unit/resolution
git commit -m "feat: project repository and entity graph state from facts"
```

### Task 7: Project call and inheritance relationships from facts

**Files:**
- Create: `src/platform_context_graph/resolution/projection/relationships.py`
- Modify: `src/platform_context_graph/resolution/orchestration/engine.py`
- Test: `tests/unit/resolution/test_fact_projection_relationships.py`
- Test: `tests/integration/indexing/test_fact_projection_relationship_parity.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- call relationship projection from parsed entity/import facts
- inheritance projection from parsed entity facts

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_relationships.py tests/integration/indexing/test_fact_projection_relationship_parity.py -q`
Expected: FAIL because the relationship projection path does not exist yet.

- [ ] **Step 3: Implement relationship projection**

Bridge the current canonical `graph/persistence` relationship helpers behind
fact-driven orchestration instead of collector-owned orchestration.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_relationships.py tests/integration/indexing/test_fact_projection_relationship_parity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution tests/unit/resolution tests/integration/indexing
git commit -m "feat: project graph relationships from facts"
```

## Chunk 5: Workloads, Platforms, And Switch-Over

### Task 8: Drive workload and platform materialization from facts

**Files:**
- Modify: `src/platform_context_graph/resolution/workloads/materialization.py`
- Modify: `src/platform_context_graph/resolution/platforms.py`
- Create: `src/platform_context_graph/resolution/projection/workloads.py`
- Test: `tests/unit/resolution/test_fact_projection_workloads.py`
- Test: `tests/unit/resolution/test_fact_projection_platforms.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- workload materialization from fact-driven inputs
- platform materialization from fact-driven inputs

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_workloads.py tests/unit/resolution/test_fact_projection_platforms.py -q`
Expected: FAIL because the fact-driven entrypoints do not exist yet.

- [ ] **Step 3: Implement fact-driven workload/platform projection**

Refactor current materialization helpers so the Resolution Engine can invoke
them from fact-backed state instead of the old collector finalize path.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_fact_projection_workloads.py tests/unit/resolution/test_fact_projection_platforms.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution tests/unit/resolution
git commit -m "feat: materialize workloads and platforms from facts"
```

### Task 9: Remove the old direct Git graph-write path

**Files:**
- Modify: `src/platform_context_graph/collectors/git/execution.py`
- Modify: `src/platform_context_graph/collectors/git/finalize.py`
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Modify: `src/platform_context_graph/indexing/coordinator_finalize.py`
- Modify: `src/platform_context_graph/cli/helpers/finalize.py`
- Test: `tests/integration/indexing/test_git_facts_end_to_end.py`
- Test: `tests/integration/indexing/test_git_facts_projection_parity.py`

- [ ] **Step 1: Write the failing integration tests**

Cover:
- Git indexing writes facts and produces graph output through the Resolution Engine
- parity on repository/file/entity/workload/platform output for a representative corpus

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_git_facts_projection_parity.py -q`
Expected: FAIL because the old direct path is still active.

- [ ] **Step 3: Cut over the Git path**

Replace direct graph finalization from the Git collector with:
- fact emission
- queue publication
- Resolution Engine projection

- [ ] **Step 4: Run the integration tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_git_facts_projection_parity.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/collectors src/platform_context_graph/indexing src/platform_context_graph/cli tests/integration/indexing
git commit -m "feat: switch git indexing to facts-first projection"
```

## Chunk 6: Docs And Final Verification

### Task 10: Update architecture and operator docs

**Files:**
- Modify: `docs/docs/architecture.md`
- Modify: `docs/docs/reference/source-layout.md`
- Modify: `src/platform_context_graph/facts/README.md`
- Modify: `src/platform_context_graph/resolution/README.md`
- Modify: `src/platform_context_graph/runtime/README.md`
- Modify: `src/platform_context_graph/app/README.md`

- [ ] **Step 1: Update docs to reflect the new runtime flow**

Document:
- facts-first Git flow
- Resolution Engine service role
- Postgres fact store and queue responsibilities

- [ ] **Step 2: Run targeted doc-adjacent tests if present**

Run: `PYTHONPATH=src:. uv run pytest tests/unit -k "phase1_imports or service_entrypoints" -q`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add docs/docs src/platform_context_graph/*/README.md
git commit -m "docs: describe phase2 facts and resolution architecture"
```

### Task 11: Run final validation sweep

**Files:**
- No code changes required unless failures are found.

- [ ] **Step 1: Run focused fact/resolution tests**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts tests/unit/resolution -q`
Expected: PASS.

- [ ] **Step 2: Run Git/indexing integration coverage**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/indexing tests/unit/indexing -q`
Expected: PASS.

- [ ] **Step 3: Run MCP/API regression slices**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/mcp/test_prompt_contract_mcp.py tests/integration/mcp/test_mcp_server.py -q`
Expected: PASS.

- [ ] **Step 4: Run repo guards**

Run:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
```

Expected: PASS.

- [ ] **Step 5: Commit any final fixes**

```bash
git add .
git commit -m "test: finalize phase2 facts-first git switch"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-02-pcg-phase2-facts-resolution.md`. Ready to execute?
