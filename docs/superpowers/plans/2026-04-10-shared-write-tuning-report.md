# Shared Graph Write Domain Tuning Report Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a repo-local command that runs the deterministic shared-write tuning sweep and prints a stable recommendation report for engineers.

**Architecture:** Keep this slice local-only. Add one script and one support module under `scripts/` that reuse the deterministic shared-projection harness from the repo test helpers, then document the command in the local testing runbook. Do not change production runtime behavior or the public CLI surface.

**Tech Stack:** Python, argparse, pytest, deterministic shared-projection test harness

---

## Chunk 1: Local Tuning Report Script

### Task 1: Add a repo-local tuning report command

**Files:**
- Create: `scripts/shared_projection_tuning_report.py`
- Create: `scripts/shared_projection_tuning_report_support.py`
- Create: `tests/unit/scripts/test_shared_projection_tuning_report.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- the support module builds a deterministic default report with scenario rows and a preferred recommendation
- the CLI prints JSON when `--format json` is selected
- the CLI prints a readable table plus recommendation when `--format table` is selected
- `--include-platform` expands the projection-domain set used in the report

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/scripts/test_shared_projection_tuning_report.py -q`

Expected: FAIL because the script and support modules do not exist yet.

- [ ] **Step 3: Implement the minimal report command**

Add:
- a support-layer report builder that:
  - seeds one balanced deterministic intent set
  - runs the tuning sweep for fixed candidate settings
  - returns a stable JSON-serializable report payload
- a CLI wrapper that:
  - supports `--format json|table`
  - supports `--include-platform`
  - writes to injectable stdout/stderr for tests
- keep the default candidate list aligned with the current docs:
  - `(1, 1)`
  - `(2, 1)`
  - `(4, 1)`
  - `(4, 2)`

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/scripts/test_shared_projection_tuning_report.py -q`

Expected: PASS.

## Chunk 2: Local Runbook

### Task 2: Document how engineers should run the tuning report

**Files:**
- Modify: `docs/docs/reference/local-testing.md`

- [ ] **Step 1: Update the runbook**

Cover:
- the exact command to run the report
- when to use JSON vs table output
- how to use `--include-platform`
- how to interpret the preferred scenario alongside shared-backlog metrics

- [ ] **Step 2: Verify the docs build**

Run:
`uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`

Expected: PASS.

## Verification Sequence

Run:

```bash
PYTHONPATH=src:. uv run pytest tests/unit/scripts/test_shared_projection_tuning_report.py tests/integration/indexing/test_shared_projection_tuning_guidance.py tests/integration/indexing/test_shared_projection_load_validation.py -q
uv run --extra dev black --check scripts/shared_projection_tuning_report.py scripts/shared_projection_tuning_report_support.py tests/unit/scripts/test_shared_projection_tuning_report.py
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```
