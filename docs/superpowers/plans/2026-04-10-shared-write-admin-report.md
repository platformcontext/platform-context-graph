# Shared Graph Write Domain Admin Report Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expose the deterministic shared-write tuning report through a real read surface so operators can fetch it through the admin API and remote CLI, not only through a local script.

**Architecture:** Move the report generator into `src/` so app code does not depend on test helpers or `scripts/`. Keep the report read-only and deterministic. The local script, admin router, and remote CLI should all share the same report builder and table formatter.

**Tech Stack:** Python, FastAPI, Typer, pytest, deterministic shared-projection simulation helpers

---

## Chunk 1: Shared Tuning Query Module

### Task 1: Create a reusable tuning report query module in `src/`

**Files:**
- Create: `src/platform_context_graph/query/shared_projection_tuning.py`
- Create: `tests/unit/query/test_shared_projection_tuning.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- `build_tuning_report()` returns the stable default scenarios and recommendation
- `build_tuning_report(include_platform=True)` expands the domain set
- `format_tuning_report_table()` renders a readable table and recommendation line

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/query/test_shared_projection_tuning.py -q`

Expected: FAIL because the query module does not exist yet.

- [ ] **Step 3: Implement the minimal query module**

Add:
- deterministic seeded shared-intent generation
- fixed candidate sweep and recommendation selection
- JSON-ready report payload builder
- reusable table formatter used by both script and CLI surfaces

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/query/test_shared_projection_tuning.py -q`

Expected: PASS.

## Chunk 2: Admin API And Remote CLI

### Task 2: Expose the report through `/api/v0/admin/shared-projection/tuning-report`

**Files:**
- Modify: `src/platform_context_graph/api/routers/admin.py`
- Modify: `tests/unit/api/test_admin_router.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- the admin router returns the report payload
- `include_platform=true` is forwarded to the report builder

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/api/test_admin_router.py -q`

Expected: FAIL because the route does not exist yet.

- [ ] **Step 3: Implement the admin endpoint**

Add:
- one read-only GET endpoint under the admin router
- no database dependency required for this deterministic report

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/unit/api/test_admin_router.py -q`

Expected: PASS.

### Task 3: Add a matching `pcg admin tuning-report` CLI surface

**Files:**
- Modify: `src/platform_context_graph/cli/commands/runtime_admin.py`
- Modify: `src/platform_context_graph/cli/remote_commands.py`
- Modify: `scripts/shared_projection_tuning_report.py`
- Modify: `scripts/shared_projection_tuning_report_support.py`
- Modify: `tests/integration/cli/test_remote_cli.py`
- Modify: `tests/unit/scripts/test_shared_projection_tuning_report.py`

- [ ] **Step 1: Write the failing tests**

Cover:
- remote CLI fetches `/api/v0/admin/shared-projection/tuning-report`
- `--include-platform` is forwarded as a query param
- local script reuses the `src/` query module rather than owning report logic

- [ ] **Step 2: Run the tests to verify they fail**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/cli/test_remote_cli.py tests/unit/scripts/test_shared_projection_tuning_report.py -q`

Expected: FAIL because the command and reuse wiring do not exist yet.

- [ ] **Step 3: Implement the remote/local CLI wiring**

Add:
- `pcg admin tuning-report`
- JSON and table rendering through the shared formatter
- remote GET path plus local fallback when no remote target is provided

- [ ] **Step 4: Run the tests to verify they pass**

Run:
`PYTHONPATH=src:. uv run pytest tests/integration/cli/test_remote_cli.py tests/unit/scripts/test_shared_projection_tuning_report.py -q`

Expected: PASS.

## Verification Sequence

Run:

```bash
PYTHONPATH=src:. uv run pytest tests/unit/query/test_shared_projection_tuning.py tests/unit/api/test_admin_router.py tests/unit/scripts/test_shared_projection_tuning_report.py tests/integration/cli/test_remote_cli.py tests/integration/indexing/test_shared_projection_tuning_guidance.py tests/integration/indexing/test_shared_projection_load_validation.py -q
uv run --extra dev black --check src/platform_context_graph/query/shared_projection_tuning.py src/platform_context_graph/api/routers/admin.py src/platform_context_graph/cli/commands/runtime_admin.py src/platform_context_graph/cli/remote_commands.py scripts/shared_projection_tuning_report.py scripts/shared_projection_tuning_report_support.py tests/unit/query/test_shared_projection_tuning.py tests/unit/api/test_admin_router.py tests/unit/scripts/test_shared_projection_tuning_report.py tests/integration/cli/test_remote_cli.py
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
git diff --check
```
