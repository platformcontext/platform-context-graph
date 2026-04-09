# Shared Graph Write Domain Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate Neo4j deadlocks caused by overlapping shared graph mutation while preserving commit-worker throughput for repo-local projection.

**Architecture:** Keep repo-local projection parallel and introduce explicit shared write domains in slices. Start by making the current write path attributable and observable, then remove global maintenance from the per-repo hot path, then add durable shared-domain intents and partitioned workers for platform and dependency writes.

**Tech Stack:** Python, pytest, Neo4j, Postgres fact work queue, facts-first resolution runtime, ripgrep

---

## Chunk 1: Write-Path Attribution And Observability

### Task 1: Unify stage names, failure classification, and query tagging across both write entrypoints

**Files:**
- Create: `src/platform_context_graph/facts/work_queue/stages.py`
- Modify: `src/platform_context_graph/resolution/orchestration/runtime.py`
- Modify: `src/platform_context_graph/indexing/coordinator_facts.py`
- Modify: `src/platform_context_graph/resolution/orchestration/engine.py`
- Modify: `src/platform_context_graph/resolution/workloads/materialization.py`
- Modify: `src/platform_context_graph/resolution/platforms.py`
- Test: `tests/unit/resolution/test_resolution_runtime_failure_persistence.py`
- Create: `tests/unit/indexing/test_inline_projection_failure_classification.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- the resolution-engine path and the ingester inline path both classify failures
  with the same stage and failure taxonomy
- shared-domain projection paths emit stable stage names for workload/platform
  finalization
- the ingester inline writer records the same deadlock metadata as the
  resolution-engine path

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_runtime_failure_persistence.py tests/unit/indexing/test_inline_projection_failure_classification.py -q`
Expected: FAIL because the ingester inline path does not classify failures or
tag them with stable stages.

- [ ] **Step 3: Implement the minimal diagnostics layer**

Add:
- a bounded stage-name helper module shared by ingester and resolution code
- shared failure classification use in `coordinator_facts.py`
- stable stage/query tagging in the shared-domain hot paths
- no new synchronous queue write per stage; keep the hot path limited to the
  existing claim/fail/complete mutation pattern

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_runtime_failure_persistence.py tests/unit/indexing/test_inline_projection_failure_classification.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts/work_queue/stages.py src/platform_context_graph/resolution/orchestration/runtime.py src/platform_context_graph/indexing/coordinator_facts.py src/platform_context_graph/resolution/orchestration/engine.py src/platform_context_graph/resolution/workloads/materialization.py src/platform_context_graph/resolution/platforms.py tests/unit/resolution/test_resolution_runtime_failure_persistence.py tests/unit/indexing/test_inline_projection_failure_classification.py
git commit -m "feat: unify projection stage diagnostics"
```

### Task 2: Surface writer attribution on admin and status paths

**Files:**
- Modify: `src/platform_context_graph/facts/work_queue/models.py`
- Modify: `src/platform_context_graph/facts/work_queue/inspection.py`
- Modify: `src/platform_context_graph/facts/work_queue/postgres.py`
- Modify: `src/platform_context_graph/api/routers/admin_facts.py`
- Modify: `src/platform_context_graph/query/status.py`
- Test: `tests/unit/facts/test_fact_work_queue_listing.py`
- Test: `tests/unit/api/test_admin_facts_router.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- admin work-item payloads include `lease_owner`
- queue listing preserves `lease_owner`
- status/admin surfaces expose enough writer attribution to distinguish
  `indexing` from `resolution-engine` for failed work

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_listing.py tests/unit/api/test_admin_facts_router.py -q`
Expected: FAIL because `lease_owner` is not serialized or asserted through the
current admin/query surfaces.

- [ ] **Step 3: Implement minimal writer attribution surfacing**

Add:
- queue listing and API serialization for `lease_owner`
- status-query wiring for the same writer attribution fields
- a verification note in the plan/docs explaining that facts-first mode has two
  writer entrypoints today

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_listing.py tests/unit/api/test_admin_facts_router.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts/work_queue src/platform_context_graph/api/routers/admin_facts.py src/platform_context_graph/query/status.py tests/unit/facts/test_fact_work_queue_listing.py tests/unit/api/test_admin_facts_router.py
git commit -m "feat: surface fact writer attribution"
```

## Chunk 2: Preserve Repo-Local Projection Boundaries

### Task 3: Stop deleting the canonical repository node during repo-local reset

**Files:**
- Modify: `src/platform_context_graph/graph/persistence/mutations.py`
- Modify: `src/platform_context_graph/resolution/orchestration/engine.py`
- Create: `tests/unit/graph/test_delete_repository_subtree.py`
- Modify: `tests/integration/indexing/test_git_facts_end_to_end.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- repo reset removes repo-owned subtree nodes but preserves the canonical `Repository` node
- shared edges attached to the `Repository` node are not dropped by the reset path
- reprojection still refreshes repo-local content deterministically

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/graph/test_delete_repository_subtree.py tests/integration/indexing/test_git_facts_end_to_end.py -q`
Expected: FAIL because the current delete path uses `DETACH DELETE r, e`.

- [ ] **Step 3: Implement the repo-local reset contract**

Add:
- a repository-subtree delete helper that preserves the `Repository` node
- targeted cleanup of repo-owned relationships and contained nodes only
- engine wiring to use the narrower reset helper

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/graph/test_delete_repository_subtree.py tests/integration/indexing/test_git_facts_end_to_end.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/graph/persistence/mutations.py src/platform_context_graph/resolution/orchestration/engine.py tests/unit/graph/test_delete_repository_subtree.py tests/integration/indexing/test_git_facts_end_to_end.py
git commit -m "feat: preserve repository nodes during reprojection"
```

### Task 4: Remove global orphan platform cleanup from the per-repo hot path

**Files:**
- Modify: `src/platform_context_graph/resolution/platforms.py`
- Modify: `src/platform_context_graph/resolution/workloads/batches.py`
- Create: `src/platform_context_graph/resolution/maintenance/platform_cleanup.py`
- Modify: `src/platform_context_graph/resolution/projection/workloads.py`
- Create: `tests/unit/resolution/test_platform_cleanup_scheduling.py`
- Modify: `tests/unit/resolution/test_platform_materialization.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- per-repo platform materialization no longer executes global orphan cleanup
- orphan cleanup runs only through the dedicated maintenance helper
- infrastructure platform writes have a single authoritative owner
- workload projection no longer duplicates infrastructure platform writes that
  the platform stage already owns

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_platform_cleanup_scheduling.py tests/unit/resolution/test_platform_materialization.py -q`
Expected: FAIL because the current per-repo path still calls `delete_orphan_platform_rows`.

- [ ] **Step 3: Implement the maintenance split**

Add:
- a maintenance module that owns global platform orphan cleanup
- repo-path materialization that skips global cleanup entirely
- explicit metrics separating repo-local cleanup from maintenance cleanup
- a single authoritative owner for infrastructure platform mutation, with tests
  forbidding duplicate writers

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_platform_cleanup_scheduling.py tests/unit/resolution/test_platform_materialization.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution/platforms.py src/platform_context_graph/resolution/workloads/batches.py src/platform_context_graph/resolution/maintenance tests/unit/resolution
git commit -m "feat: move orphan platform cleanup out of repo projection"
```

## Chunk 3: Durable Shared-Domain Inputs

### Task 5: Add durable shared projection intents in shadow mode

**Files:**
- Create: `src/platform_context_graph/resolution/shared_projection/models.py`
- Create: `src/platform_context_graph/resolution/shared_projection/postgres.py`
- Create: `src/platform_context_graph/resolution/shared_projection/schema.py`
- Modify: `src/platform_context_graph/resolution/workloads/materialization.py`
- Modify: `src/platform_context_graph/resolution/platforms.py`
- Test: `tests/unit/resolution/test_shared_projection_intents.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- repo-local projection emits durable shared-domain intent rows while existing
  shared-domain writes remain authoritative
- intent rows carry `projection_domain`, `partition_key`, `repository_id`, `source_run_id`, and `generation_id`
- repeated emission is idempotent per repository plus generation, not just per
  repo/run

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_projection_intents.py -q`
Expected: FAIL because shared projection intent storage does not exist.

- [ ] **Step 3: Implement minimal durable intent storage**

Add:
- Postgres-backed shared projection intent schema and models
- helper APIs to upsert and list intent rows
- repo-local emitters for platform and dependency intent payloads
- shadow-mode emission only; do not cut over shared-domain writes in this task

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_projection_intents.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution/shared_projection src/platform_context_graph/resolution/workloads/materialization.py src/platform_context_graph/resolution/platforms.py tests/unit/resolution/test_shared_projection_intents.py
git commit -m "feat: add durable shared projection intents"
```

### Task 6: Add parent/child completion semantics for repo projection and shared-domain follow-up

**Files:**
- Modify: `src/platform_context_graph/facts/work_queue/models.py`
- Modify: `src/platform_context_graph/facts/work_queue/schema.py`
- Modify: `src/platform_context_graph/facts/work_queue/claims.py`
- Modify: `src/platform_context_graph/indexing/coordinator_facts.py`
- Modify: `src/platform_context_graph/query/status.py`
- Modify: `src/platform_context_graph/runtime/status_store_db.py`
- Modify: `src/platform_context_graph/api/routers/admin_facts.py`
- Test: `tests/unit/facts/test_fact_work_queue_failure_metadata.py`
- Test: `tests/unit/query/test_status.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- parent repo-projection work items can reference child shared-domain work
- status surfaces do not report completed while authoritative child shared work
  is still pending
- older child generations are ignored once a newer generation is accepted
- shadow-mode intents do not block repo completion before a domain is cut over

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_failure_metadata.py tests/unit/query/test_status.py tests/unit/indexing/test_coordinator_facts.py tests/unit/runtime/test_status_store_db.py -q`
Expected: FAIL because the queue and status model do not express parent/child shared-domain completion.

- [ ] **Step 3: Implement the minimal completion contract**

Add:
- parent/child linkage fields or equivalent durable domain-state records
- queue helpers to mark shared-domain children complete
- status/query surface updates exposing `shared_projection_pending`
- ingester fact-run completion fencing so async shared work cannot report
  completed too early
- runtime repository coverage/status-store fencing for the same completion model
- authoritative-domain gating so only cut-over domains participate in
  completion blocking while shadow-mode domains remain observational

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_failure_metadata.py tests/unit/query/test_status.py tests/unit/indexing/test_coordinator_facts.py tests/unit/runtime/test_status_store_db.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts/work_queue src/platform_context_graph/indexing/coordinator_facts.py src/platform_context_graph/query/status.py src/platform_context_graph/runtime/status_store_db.py src/platform_context_graph/api/routers/admin_facts.py tests/unit/facts/test_fact_work_queue_failure_metadata.py tests/unit/query/test_status.py tests/unit/indexing/test_coordinator_facts.py tests/unit/runtime/test_status_store_db.py
git commit -m "feat: add shared projection completion semantics"
```

## Chunk 4: Partitioned Shared-Domain Execution

### Task 7: Add partitioned shared-domain workers for platform projection

**Files:**
- Create: `src/platform_context_graph/resolution/shared_projection/partitioning.py`
- Create: `src/platform_context_graph/resolution/shared_projection/runtime.py`
- Modify: `src/platform_context_graph/resolution/platforms.py`
- Test: `tests/unit/resolution/test_shared_projection_partitioning.py`
- Test: `tests/unit/resolution/test_shared_platform_runtime.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- platform intents map to a stable `platform_id` partition
- the same `platform_id` never runs concurrently in two worker partitions
- different `platform_id` values can make progress concurrently
- stale generations retract old platform edges authoritatively by repository plus generation
- worker cutover replaces shadow-mode inline authority for the platform domain

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_projection_partitioning.py tests/unit/resolution/test_shared_platform_runtime.py -q`
Expected: FAIL because the shared-domain worker runtime does not exist.

- [ ] **Step 3: Implement minimal partitioned platform execution**

Add:
- stable partition-key calculation
- durable worker claims for shared projection intents
- authoritative platform-edge retract/upsert execution
- platform-domain cutover from shadow mode to worker-owned execution

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_projection_partitioning.py tests/unit/resolution/test_shared_platform_runtime.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution/shared_projection src/platform_context_graph/resolution/platforms.py tests/unit/resolution/test_shared_projection_partitioning.py tests/unit/resolution/test_shared_platform_runtime.py
git commit -m "feat: add partitioned shared platform projection"
```

### Task 8: Add partitioned shared-domain workers for dependency projection

**Files:**
- Modify: `src/platform_context_graph/resolution/workloads/materialization.py`
- Modify: `src/platform_context_graph/resolution/workloads/batches.py`
- Modify: `src/platform_context_graph/resolution/shared_projection/runtime.py`
- Test: `tests/unit/resolution/test_shared_dependency_runtime.py`
- Test: `tests/integration/indexing/test_concurrent_shared_projection.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- dependency intents partition by stable dependency key
- retract authority belongs to source repository plus generation
- different dependency keys can make progress concurrently
- concurrent overlapping repo projections do not deadlock and converge to the same final dependency graph

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_dependency_runtime.py tests/integration/indexing/test_concurrent_shared_projection.py -q`
Expected: FAIL because dependency writes still happen inline in repo projection.

- [ ] **Step 3: Implement minimal partitioned dependency execution**

Add:
- partitioned dependency worker support
- authoritative retract generation fencing
- integration hook from repo-local projection completion into shared dependency execution
- dependency-domain cutover from shadow mode to worker-owned execution

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_shared_dependency_runtime.py tests/integration/indexing/test_concurrent_shared_projection.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution/workloads src/platform_context_graph/resolution/shared_projection tests/unit/resolution/test_shared_dependency_runtime.py tests/integration/indexing/test_concurrent_shared_projection.py
git commit -m "feat: add partitioned shared dependency projection"
```

## Chunk 5: Rollout Validation And Runtime Integration

### Task 9: Validate equivalent graph output across ingester-inline and resolution-engine entrypoints

**Files:**
- Modify: `tests/integration/indexing/test_git_facts_end_to_end.py`
- Create: `tests/integration/indexing/test_split_runtime_projection_equivalence.py`
- Modify: `docs/docs/architecture.md`

- [ ] **Step 1: Write the failing tests**

Cover:
- ingester-inline repo-local projection plus shared-domain follow-up matches resolution-engine initiated projection
- status surfaces remain honest while shared-domain work is pending
- architecture docs reflect the new write-domain contract

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_split_runtime_projection_equivalence.py -q`
Expected: FAIL because the new shared-domain completion contract is not yet wired end to end.

- [ ] **Step 3: Implement the final integration wiring**

Add:
- shared-domain follow-up execution from both runtime entrypoints
- final status projection updates
- architecture documentation updates for deployed write-domain flow

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_git_facts_end_to_end.py tests/integration/indexing/test_split_runtime_projection_equivalence.py -q`
Expected: PASS.

- [ ] **Step 5: Run the broader verification bundle**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts tests/unit/indexing tests/unit/resolution tests/unit/api tests/unit/query tests/unit/runtime tests/integration/indexing -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/platform_context_graph tests docs/docs/architecture.md
git commit -m "feat: finalize shared graph write domain execution"
```

Plan complete and saved to `docs/superpowers/plans/2026-04-09-shared-graph-write-domain-implementation.md`. Ready to execute.
