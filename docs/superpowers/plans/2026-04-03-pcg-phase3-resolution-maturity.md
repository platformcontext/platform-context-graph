# PCG Phase 3 Resolution Maturity Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mature the facts-first runtime with durable failure taxonomy, richer replay and recovery controls, and explainable provenance and confidence records for projected graph outputs.

**Architecture:** Extend the Postgres-backed fact queue with durable failure state and replay audit records, add stronger admin and CLI recovery controls, then introduce a small projection decision store that captures evidence and confidence for important resolution outputs. Keep the three-service architecture intact while improving trust, operability, and explainability.

**Tech Stack:** Python, pytest, Postgres, existing PCG API/admin/CLI/runtime stack, facts-first Resolution Engine, OTEL telemetry, ripgrep

---

## Chunk 1: Failure Taxonomy Foundation

### Task 1: Add durable failure metadata to fact work items

**Files:**
- Modify: `src/platform_context_graph/facts/work_queue/models.py`
- Modify: `src/platform_context_graph/facts/work_queue/postgres.py`
- Create: `src/platform_context_graph/facts/work_queue/failure_types.py`
- Test: `tests/unit/facts/test_fact_work_queue_failure_metadata.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- row models carrying durable failure fields
- queue writes preserving stage, class, code, and retry disposition
- dead-letter timestamps and next-retry timestamps

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_failure_metadata.py -q`
Expected: FAIL because the new failure metadata fields and helpers do not exist yet.

- [ ] **Step 3: Implement the minimal failure metadata layer**

Add:
- stable failure type enums/constants
- richer work-item row models
- Postgres persistence for new durable fields

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_work_queue_failure_metadata.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts/work_queue tests/unit/facts/test_fact_work_queue_failure_metadata.py
git commit -m "feat: add durable fact work failure metadata"
```

### Task 2: Classify resolution-engine failures before persistence

**Files:**
- Modify: `src/platform_context_graph/resolution/orchestration/runtime.py`
- Create: `src/platform_context_graph/resolution/orchestration/failure_classification.py`
- Test: `tests/unit/resolution/test_resolution_failure_classification.py`
- Test: `tests/unit/resolution/test_resolution_runtime_failure_persistence.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- classifying exceptions into stable failure classes
- runtime persisting stage and disposition on failure
- dead-letter promotion after policy thresholds

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_failure_classification.py tests/unit/resolution/test_resolution_runtime_failure_persistence.py -q`
Expected: FAIL because the classifier and richer runtime persistence do not exist yet.

- [ ] **Step 3: Implement minimal runtime failure classification**

Add:
- a classifier mapping known exception families to stable failure classes
- runtime updates for attempt start/finish and failure persistence
- policy hooks for retry vs terminal handling

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_resolution_failure_classification.py tests/unit/resolution/test_resolution_runtime_failure_persistence.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution src/platform_context_graph/facts/work_queue tests/unit/resolution
git commit -m "feat: classify and persist resolution failures"
```

## Chunk 2: Replay, Dead-Letter, And Backfill Controls

### Task 3: Add durable replay events and richer queue recovery helpers

**Files:**
- Modify: `src/platform_context_graph/facts/work_queue/replay.py`
- Create: `src/platform_context_graph/facts/work_queue/replay_events.py`
- Modify: `src/platform_context_graph/facts/work_queue/postgres.py`
- Test: `tests/unit/facts/test_fact_replay_events.py`
- Test: `tests/unit/facts/test_fact_work_queue_recovery.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- replay events recorded with operator note and selector details
- dead-letter promotion and revival behavior
- backfill request creation and replay scope validation

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_replay_events.py tests/unit/facts/test_fact_work_queue_recovery.py -q`
Expected: FAIL because replay event persistence and recovery helpers are incomplete.

- [ ] **Step 3: Implement replay event and recovery storage**

Add:
- replay event row models
- Postgres persistence for operator recovery actions
- queue helpers for replay, dead-letter, and backfill state transitions

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts/test_fact_replay_events.py tests/unit/facts/test_fact_work_queue_recovery.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/facts/work_queue tests/unit/facts
git commit -m "feat: add replay events and recovery helpers"
```

### Task 4: Expand admin API and CLI recovery controls

**Files:**
- Modify: `src/platform_context_graph/api/routers/admin.py`
- Modify: `src/platform_context_graph/cli/commands/runtime_admin.py`
- Test: `tests/integration/api/test_admin_facts_recovery.py`
- Test: `tests/unit/cli/test_runtime_admin_facts_recovery.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- listing failed/dead-lettered work with durable failure fields
- replaying by work item, repository, and failure class
- terminalizing or reviving dead-lettered items with operator notes

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/api/test_admin_facts_recovery.py tests/unit/cli/test_runtime_admin_facts_recovery.py -q`
Expected: FAIL because the richer admin and CLI controls do not exist yet.

- [ ] **Step 3: Implement the minimal recovery control surface**

Add:
- richer admin API selectors and response fields
- CLI subcommands/options for replay, dead-letter, revive, and backfill
- validation to require explicit selectors for bulk actions

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/integration/api/test_admin_facts_recovery.py tests/unit/cli/test_runtime_admin_facts_recovery.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/api src/platform_context_graph/cli tests/integration/api tests/unit/cli
git commit -m "feat: expand admin and cli facts recovery controls"
```

## Chunk 3: Provenance And Confidence

### Task 5: Add projection decision models and storage

**Files:**
- Create: `src/platform_context_graph/resolution/decisions/__init__.py`
- Create: `src/platform_context_graph/resolution/decisions/models.py`
- Create: `src/platform_context_graph/resolution/decisions/postgres.py`
- Test: `tests/unit/resolution/test_projection_decision_store.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- storing projection decisions with evidence references
- loading decisions by repository and source run
- preserving confidence score and rationale

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_projection_decision_store.py -q`
Expected: FAIL because the decision store does not exist yet.

- [ ] **Step 3: Implement the minimal decision store**

Add:
- decision and evidence row models
- Postgres schema bootstrap
- insert/read APIs for projection decisions

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_projection_decision_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution/decisions tests/unit/resolution/test_projection_decision_store.py
git commit -m "feat: add projection decision store"
```

### Task 6: Record provenance and confidence for workload, platform, and relationship projection

**Files:**
- Modify: `src/platform_context_graph/resolution/projection/workloads.py`
- Modify: `src/platform_context_graph/resolution/projection/platforms.py`
- Modify: `src/platform_context_graph/resolution/projection/relationships.py`
- Modify: `src/platform_context_graph/resolution/orchestration/engine.py`
- Test: `tests/unit/resolution/test_projection_confidence.py`
- Test: `tests/integration/indexing/test_projection_decision_records.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- workload and platform projection writing decision records
- relationship projection attaching evidence and confidence
- projected outputs remaining functionally correct while adding decision records

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_projection_confidence.py tests/integration/indexing/test_projection_decision_records.py -q`
Expected: FAIL because projection does not yet write decision records or confidence metadata.

- [ ] **Step 3: Implement the minimal confidence layer**

Add:
- bounded confidence scoring helpers
- evidence aggregation for direct, corroborating, and inferred inputs
- decision writes from the projection engine for the selected output families

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/resolution/test_projection_confidence.py tests/integration/indexing/test_projection_decision_records.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/resolution tests/unit/resolution tests/integration/indexing
git commit -m "feat: record projection provenance and confidence"
```

## Chunk 4: Telemetry, Docs, And Final Validation

### Task 7: Extend observability for failure and confidence maturity

**Files:**
- Modify: `src/platform_context_graph/observability/fact_resolution_metrics.py`
- Modify: `src/platform_context_graph/observability/facts_first_logs.py`
- Modify: `src/platform_context_graph/resolution/orchestration/runtime.py`
- Test: `tests/unit/observability/test_phase3_fact_resolution_metrics.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- failure metrics by stage and failure class
- replay and dead-letter counters
- confidence-band metrics or logs where appropriate

- [ ] **Step 2: Run the tests to verify they fail**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/observability/test_phase3_fact_resolution_metrics.py -q`
Expected: FAIL because the Phase 3 maturity telemetry does not exist yet.

- [ ] **Step 3: Implement the minimal observability additions**

Add:
- stable metric names and labels for failure and replay state
- richer lifecycle logging for operator actions and terminal work items
- confidence-band telemetry where it aids tuning and drift detection

- [ ] **Step 4: Run the tests to verify they pass**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/observability/test_phase3_fact_resolution_metrics.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/platform_context_graph/observability src/platform_context_graph/resolution tests/unit/observability
git commit -m "feat: extend phase3 facts-first observability"
```

### Task 8: Update docs and run the full Phase 3 validation sweep

**Files:**
- Modify: `docs/docs/architecture.md`
- Modify: `docs/docs/roadmap.md`
- Modify: `docs/docs/reference/telemetry/metrics.md`
- Modify: `docs/docs/reference/telemetry/logs.md`
- Modify: `docs/docs/reference/telemetry/traces.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/reference/local-testing.md`
- Modify: `src/platform_context_graph/facts/README.md`
- Modify: `src/platform_context_graph/resolution/README.md`
- Modify: `src/platform_context_graph/api/README.md`
- Modify: `src/platform_context_graph/cli/README.md`

- [ ] **Step 1: Update the docs to match the final Phase 3 behavior**

Cover:
- recovery controls and operator flows
- projection decision storage and confidence semantics
- updated local and staging validation guidance

- [ ] **Step 2: Run targeted Python tests**

Run: `PYTHONPATH=src:. uv run pytest tests/unit/facts tests/unit/resolution tests/unit/observability tests/unit/cli tests/integration/api/test_admin_facts_recovery.py tests/integration/indexing/test_projection_decision_records.py -q`
Expected: PASS.

- [ ] **Step 3: Run docs and quality checks**

Run:
- `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`
- `python -m py_compile $(rg --files src tests | rg '\\.py$')`
- `git diff --check`

Expected: PASS.

- [ ] **Step 4: Run the full test-instance validation checklist**

Use the updated local-testing and service-runtimes docs to validate:
- API
- Ingester
- Resolution Engine
- replay and dead-letter controls
- confidence/provenance visibility
- telemetry and dashboards

- [ ] **Step 5: Commit**

```bash
git add docs src
git commit -m "docs: finalize phase3 resolution maturity guidance"
```

## Execution Notes

- Keep all Phase 3 work on `codex/phase3-resolution-maturity`.
- Do not split Phase 3 across multiple PRs.
- Implement the chunks in order even though they land in one branch.
- Prefer small focused modules over growing already-large runtime files.
- Remove stale code instead of preserving backwards-compatibility behavior.
