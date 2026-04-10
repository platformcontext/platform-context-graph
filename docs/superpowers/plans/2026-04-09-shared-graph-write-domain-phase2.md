# Shared Graph Write Domain Phase 2

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans or superpowers:subagent-driven-development when implementing this plan. Steps use checkbox syntax for tracking.

**Goal:** Validate and operationalize the shared-write architecture that already landed in phase 1 by adding direct visibility into shared-domain backlog and then using that visibility to drive safe performance tuning.

**Why now:** Phase 1 removed the largest deadlock risks, but live ops-qa work showed that queue metrics alone are not enough to answer whether platform/dependency follow-up work is healthy, stalled, or silently building up behind the scenes.

**Architecture:** Keep the phase-1 ownership split intact. Do not re-open the shared-write cutover itself in this phase. Add observability first, then validation harnesses, then rollout guidance.

**Tech Stack:** Python, pytest, OpenTelemetry metrics, Postgres shared intent store, ripgrep

---

## Chunk 1: Shared Projection Observability

### Task 1: Expose shared-domain backlog depth and age as first-class metrics

**Files:**
- Modify: `src/platform_context_graph/resolution/shared_projection/postgres.py`
- Modify: `src/platform_context_graph/observability/fact_resolution_instruments.py`
- Modify: `src/platform_context_graph/observability/fact_resolution_observers.py`
- Modify: `src/platform_context_graph/observability/runtime.py`
- Create: `tests/unit/observability/test_shared_projection_telemetry.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- backlog depth is exported per shared projection domain
- oldest pending age is exported per shared projection domain
- empty stores emit no stale shared-projection observations
- labels remain bounded to shared domain and component, not repository identity

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/observability/test_shared_projection_telemetry.py -q`

Expected: FAIL because no shared-projection gauges exist yet and the shared intent
store does not expose aggregate snapshot helpers.

- [ ] **Step 3: Implement minimal shared backlog observability**

Add:
- store helpers that return aggregate pending depth and oldest age grouped by
  `projection_domain`
- observable runtime state for shared backlog gauges
- OTEL gauges for:
  - `pcg_shared_projection_pending_intents`
  - `pcg_shared_projection_oldest_pending_age_seconds`
- refresh wiring that can run from the existing facts/resolution sampling path

Do not add repository labels or high-cardinality dimensions.

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/observability/test_shared_projection_telemetry.py -q`

Expected: PASS.

### Task 2: Fold shared backlog snapshots into runtime status sampling

**Files:**
- Modify: `src/platform_context_graph/resolution/orchestration/runtime.py`
- Modify: `src/platform_context_graph/query/status_shared_projection.py`
- Modify: `tests/unit/observability/test_resolution_queue_sampler.py`
- Modify: `tests/unit/query/test_status_shared_projection.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- the independent queue sampler refreshes shared backlog gauges when a queue
  exposes shared intent metrics
- shared-projection pending status remains consistent with the new aggregate
  backlog snapshot
- status paths continue to work when the shared intent store is unavailable

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/observability/test_resolution_queue_sampler.py tests/unit/query/test_status_shared_projection.py -q`

Expected: FAIL because shared backlog sampling is not wired into runtime
observability.

- [ ] **Step 3: Implement runtime/status wiring**

Add:
- one bounded refresh hook from the existing queue sampler
- compatibility behavior for queue-only test doubles
- shared backlog state updates that reuse the current observability runtime lock

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/observability/test_resolution_queue_sampler.py tests/unit/query/test_status_shared_projection.py -q`

Expected: PASS.

## Chunk 2: Validation Harness

### Task 3: Add a repeatable concurrent shared-write validation harness

**Files:**
- Create: `tests/integration/indexing/test_shared_projection_observability.py`
- Modify: `tests/integration/indexing/test_split_runtime_projection_equivalence.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- concurrent shared follow-up runs converge to the same authoritative graph
- shared backlog metrics return to zero after convergence
- pending age does not stay stuck once follow-up completes

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_observability.py tests/integration/indexing/test_split_runtime_projection_equivalence.py -q`

Expected: FAIL because the observability assertions do not exist yet.

- [ ] **Step 3: Implement the harness**

Add:
- a narrow integration fixture that emits shared intents, drains follow-up, and
  asserts both graph equivalence and telemetry convergence
- no synthetic benchmark loops in this task; keep it deterministic and CI-safe

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_observability.py tests/integration/indexing/test_split_runtime_projection_equivalence.py -q`

Expected: PASS.

## Chunk 3: Rollout Interpretation

### Task 4: Document the operator contract for shared-write metrics

**Files:**
- Modify: `docs/docs/reference/telemetry/index.md`
- Modify: `docs/docs/architecture.md`

- [ ] **Step 1: Write the docs update**

Cover:
- what the new shared-projection gauges mean
- how they differ from fact queue depth
- when to use metrics vs logs vs traces for shared-write debugging
- recommended first checks during staging/prod rollout validation

- [ ] **Step 2: Verify the docs build**

Run:
`uv run mkdocs build --strict`

Expected: PASS.

---

## Verification Sequence

Run the narrow test slice as each task lands, then finish with:

```bash
PYTHONPATH=src:. uv run pytest tests/unit/observability/test_shared_projection_telemetry.py tests/unit/observability/test_resolution_queue_sampler.py tests/unit/query/test_status_shared_projection.py -q
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run --extra dev black --check src/platform_context_graph/observability src/platform_context_graph/resolution/shared_projection tests/unit/observability tests/unit/query
git diff --check
```

If Task 3 lands in the same session, also run the targeted integration slice from
`docs/docs/reference/local-testing.md`.
