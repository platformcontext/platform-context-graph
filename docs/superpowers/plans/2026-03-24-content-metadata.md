# Raw Content Metadata Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist and expose metadata for templated and IaC-related raw content without changing the existing content API shape beyond additive fields and filters.

**Architecture:** Use one shared classifier to derive file metadata from raw source, persist that metadata on both file and entity content rows, and expose it through the existing HTTP and MCP content read/search surfaces. Roll existing data forward with a batch backfill job instead of forcing repository reindex.

**Tech Stack:** Python, FastAPI, psycopg, pytest

---

### Task 1: Shared metadata classifier

**Files:**
- Modify: `src/platform_context_graph/tools/languages/templated_detection.py`
- Test: `tests/unit/parsers/test_templated_detection.py`

- [ ] Add a production helper that infers persisted metadata from `relative_path + content`.
- [ ] Normalize artifact families and template dialects for persisted use.
- [ ] Keep ambiguous files fail-closed for `template_dialect`.
- [ ] Run: `env PYTHONPATH=src:. /Users/allen/personal-repos/platform-context-graph/.venv/bin/python -m pytest -q tests/unit/parsers/test_templated_detection.py`

### Task 2: Persist metadata during content ingest

**Files:**
- Modify: `src/platform_context_graph/content/models.py`
- Modify: `src/platform_context_graph/content/ingest.py`
- Test: `tests/unit/content/test_ingest.py`

- [ ] Extend file and entity content models with metadata fields.
- [ ] Classify each file once during content entry preparation.
- [ ] Propagate file metadata to all derived entity rows.
- [ ] Run: `env PYTHONPATH=src:. /Users/allen/personal-repos/platform-context-graph/.venv/bin/python -m pytest -q tests/unit/content/test_ingest.py`

### Task 3: Query and contract plumbing

**Files:**
- Modify: `src/platform_context_graph/content/postgres.py`
- Modify: `src/platform_context_graph/content/service.py`
- Modify: `src/platform_context_graph/query/content.py`
- Modify: `src/platform_context_graph/domain/responses.py`
- Modify: `src/platform_context_graph/api/routers/content.py`
- Modify: `src/platform_context_graph/mcp/content_tools.py`
- Modify: `src/platform_context_graph/mcp/tools/content.py`
- Test: `tests/unit/content/test_postgres.py`
- Test: `tests/unit/content/test_service.py`
- Test: `tests/integration/api/test_content_api.py`
- Test: `tests/integration/mcp/test_content_tools.py`

- [ ] Add metadata columns and indexes to the Postgres schema bootstrap.
- [ ] Persist metadata on file/entity writes and return it on file/entity reads.
- [ ] Add metadata filters to file/entity search.
- [ ] Extend existing API and MCP schemas without introducing new endpoints or tools.
- [ ] Run: `env PYTHONPATH=src:. /Users/allen/personal-repos/platform-context-graph/.venv/bin/python -m pytest -q tests/unit/content/test_postgres.py tests/unit/content/test_service.py tests/integration/api/test_content_api.py tests/integration/mcp/test_content_tools.py`

### Task 4: Backfill existing rows

**Files:**
- Create: `scripts/backfill_content_metadata.py`
- Create: `scripts/backfill_content_metadata_support.py`
- Test: `tests/unit/scripts/test_backfill_content_metadata.py`

- [ ] Add a batch-driven backfill runner over existing `content_files` rows.
- [ ] Cascade file metadata to entity rows by `(repo_id, relative_path)`.
- [ ] Support `--dry-run`, `--batch-size`, `--repo-id`, and `--limit`.
- [ ] Make reruns idempotent.
- [ ] Run: `env PYTHONPATH=src:. /Users/allen/personal-repos/platform-context-graph/.venv/bin/python -m pytest -q tests/unit/scripts/test_backfill_content_metadata.py`

### Task 5: Fixture-driven validation and docs

**Files:**
- Create: `docs/superpowers/specs/2026-03-24-content-metadata-design.md`
- Create: `docs/superpowers/plans/2026-03-24-content-metadata.md`
- Reuse: `tests/fixtures/templated_iac_corpus/`

- [ ] Document the raw-canonical metadata design and the rendered-artifacts boundary.
- [ ] Run the focused fixture-backed suite:
  `env PYTHONPATH=src:. /Users/allen/personal-repos/platform-context-graph/.venv/bin/python -m pytest -q tests/unit/parsers/test_templated_detection.py tests/unit/content/test_ingest.py tests/unit/content/test_postgres.py tests/unit/content/test_service.py tests/unit/scripts/test_backfill_content_metadata.py tests/integration/api/test_content_api.py tests/integration/mcp/test_content_tools.py`
- [ ] Run a local Compose E2E against `tests/fixtures/templated_iac_corpus` and verify metadata-filtered content search.
