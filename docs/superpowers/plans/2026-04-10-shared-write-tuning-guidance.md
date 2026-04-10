# Shared Graph Write Domain Tuning Guidance Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the deterministic shared-write load harness into a repeatable tuning matrix that compares partition and batch settings, then document concrete rollout guidance from those results.

**Architecture:** Keep production runtime behavior unchanged in this slice. Extend the integration harness with a deterministic sweep helper that measures drain rounds and per-round work distribution for a fixed workload shape, then publish the findings as operator guidance in the existing telemetry and architecture docs.

**Tech Stack:** Python, pytest, shared projection runtime helpers, MkDocs

---

## Chunk 1: Tuning Matrix Harness

### Task 1: Add deterministic sweep helpers for partition and batch tuning

**Files:**
- Modify: `tests/integration/indexing/shared_projection_load_harness.py`
- Create: `tests/integration/indexing/test_shared_projection_tuning_guidance.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- a tuning sweep can compare multiple `(partition_count, batch_limit)` settings against the same seeded intent set
- the helper returns deterministic round counts, processed totals, and peak pending backlog
- the helper can identify the best setting by lowest round count, then by highest average per-round throughput

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_tuning_guidance.py -q`

Expected: FAIL because no tuning sweep helper exists yet.

- [ ] **Step 3: Implement the minimal harness support**

Add:
- a `TuningScenarioResult` value object
- one helper that runs `drain_until_empty()` for a list of candidate settings against identical seeded intents
- deterministic derived fields:
  - `round_count`
  - `processed_total`
  - `peak_pending_total`
  - `mean_processed_per_round`
- one selector helper that returns the preferred candidate using stable tie-breaking

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_tuning_guidance.py -q`

Expected: PASS.

## Chunk 2: Rollout Guidance

### Task 2: Document the current shared-write tuning guidance

**Files:**
- Modify: `docs/docs/reference/telemetry/index.md`
- Modify: `docs/docs/architecture.md`

- [ ] **Step 1: Update the docs**

Cover:
- what the deterministic tuning matrix tells us today
- how to compare partition count changes safely in staging
- how batch size changes affect drain rounds vs per-round work
- which metrics to watch first during tuning:
  - `pcg_shared_projection_pending_intents`
  - `pcg_shared_projection_oldest_pending_age_seconds`
  - `pcg_fact_queue_depth`
  - `pcg_fact_queue_oldest_age_seconds`
- the current default operator advice:
  - prefer increasing partition count before increasing batch size
  - keep batch size modest unless backlog clears but round count remains high

- [ ] **Step 2: Verify the docs build**

Run:
`uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`

Expected: PASS.

## Verification Sequence

Run:

```bash
PYTHONPATH=src:. uv run pytest tests/integration/indexing/test_shared_projection_tuning_guidance.py tests/integration/indexing/test_shared_projection_load_validation.py tests/integration/indexing/test_shared_projection_observability.py tests/integration/indexing/test_split_runtime_projection_equivalence.py tests/integration/indexing/test_concurrent_shared_projection.py -q
uv run --extra dev black --check tests/integration/indexing/test_shared_projection_tuning_guidance.py tests/integration/indexing/shared_projection_load_harness.py
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```
