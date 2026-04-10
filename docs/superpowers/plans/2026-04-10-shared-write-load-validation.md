# Shared Graph Write Domain Load Validation

> **For agentic workers:** REQUIRED: Use superpowers:executing-plans or superpowers:subagent-driven-development when implementing this plan. Steps use checkbox syntax for tracking.

**Goal:** Add a deterministic validation harness that proves shared-domain backlog drains predictably under partitioned worker pressure without relying on flaky wall-clock thresholds.

**Why now:** Phase 2 added shared backlog metrics and status visibility. The next gap is confidence that those signals actually reflect healthy drain behavior when shared-domain work arrives in larger batches across multiple partitions.

**Architecture:** Reuse the phase-1 shared follow-up runtime. Do not add production benchmark loops. Keep the harness deterministic, CI-safe, and centered on partitioned drain rounds plus backlog convergence.

**Tech Stack:** Python, pytest, OpenTelemetry metrics, shared projection runtime helpers

---

## Chunk 1: Deterministic Drain Harness

### Task 1: Build reusable integration harness helpers for partitioned drain rounds

**Files:**
- Create: `tests/integration/indexing/shared_projection_load_harness.py`

- [ ] **Step 1: Write the helper scaffold**

Add:
- in-memory shared intent store with source-run-aware backlog snapshots
- queue stub with accepted generations and pending-repository counting
- balanced intent builders for repo, workload, and platform projection domains
- round-by-round drain helpers that record pending backlog after each round

- [ ] **Step 2: Verify the helper is used by failing tests**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_load_validation.py -q`

Expected: FAIL because the validation tests do not exist yet.

## Chunk 2: Integration Validation

### Task 2: Prove balanced partitioning reduces drain rounds and clears backlog metrics

**Files:**
- Create: `tests/integration/indexing/test_shared_projection_load_validation.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- balanced dependency intents drain in fewer rounds with multiple partitions than with one partition
- backlog depth decreases monotonically round to round until zero
- shared backlog metrics clear after the multi-partition drain completes
- source-run status backlog stays aligned with pending domain snapshots during drain

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_load_validation.py -q`

Expected: FAIL because the harness and assertions do not exist yet.

- [ ] **Step 3: Implement the harness and assertions**

Add:
- one dependency-focused test that compares single-partition and multi-partition drain rounds
- one mixed-domain test that validates status backlog alignment while repo, workload, and platform domains drain together
- metric sampling through the shared backlog gauges rather than direct store inspection alone

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_load_validation.py -q`

Expected: PASS.

## Verification Sequence

Run:

```bash
PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_load_validation.py tests/integration/indexing/test_shared_projection_observability.py tests/integration/indexing/test_split_runtime_projection_equivalence.py tests/integration/indexing/test_concurrent_shared_projection.py -q
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run --extra dev black --check tests/integration/indexing
git diff --check
```
