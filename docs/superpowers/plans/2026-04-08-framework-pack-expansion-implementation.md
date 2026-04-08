# Framework Pack Expansion Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the parser-maturity branch from the completed React/Next.js lane into a reusable framework-pack program with concrete Node and Python framework support, provider-pack groundwork, and repeatable end-to-end validation.

**Architecture:** Keep syntax parsing and framework semantics separate. Parser frontends continue to produce bounded syntax facts, declarative framework packs map those facts into higher-level semantics, file-node persistence stores the bounded results, and repository/investigation surfaces summarize them back to users. Each new lane should reuse the same pack-loading, projection, summary, and validation pattern proven by the React/Next.js slice.

**Tech Stack:** Python, pytest, YAML-backed pack specs, tree-sitter parser outputs, FalkorDB-backed indexing/query validation, MkDocs docs, `uv`

---

## Scope

This plan covers the remaining concrete work that still fits cleanly on `codex/parser-framework-maturity-next`.

Already complete on this branch:

- true TSX grammar routing and normalization
- React/Next.js semantic facts
- file-node persistence
- repo/story/investigation framework surfacing
- end-to-end validation for JavaScript, TypeScript, and TSX
- declarative React/Next.js framework-pack specs and loader
- framework-pack validation and contributor tooling
- Node HTTP framework packs for Express and Hapi
- Node HTTP file-node persistence and repo/story/investigation surfacing
- real repo smoke validation for Express and Hapi semantics

Still left for this branch:

1. add a thin Python web framework lane for FastAPI and Flask
2. create the first provider-pack foundation for JS/TS SDK evidence
3. publish repeatable framework-pack docs and validation expectations

Out of scope for this branch unless the above finishes early:

- full Django support
- full NestJS or Remix coverage
- deeper component tree analysis
- framework packs for every remaining language in one branch

## Validation Targets

Concrete local repos for this branch:

- JavaScript / Node:
  - `/Users/allen/repos/services/api-node-search-api`
  - `/Users/allen/repos/services/api-node-datastore`
  - `/Users/allen/repos/services/portal-react-platform`
  - `/Users/allen/repos/services/lambda-node-video-webapp`
- Python:
  - `/Users/allen/repos/services/recos-ranker-service`
  - `/Users/allen/repos/services/lambda-python-lb-s3-files`
  - `/Users/allen/repos/services/lambda-python-s3-proxy`
- Existing regression baselines:
  - `/Users/allen/repos/services/portal-nextjs-platform`
  - `/Users/allen/repos/services/api-node-platform`

## Chunk 1: Framework Pack Contract Hardening

Status: completed on this branch.

### Task 1: Add framework-pack validation and repo-root/package-path coverage

**Files:**
- Create: `src/platform_context_graph/parsers/framework_packs/validation.py`
- Modify: `src/platform_context_graph/parsers/framework_packs/__init__.py`
- Modify: `src/platform_context_graph/parsers/framework_packs/catalog.py`
- Modify: `src/platform_context_graph/parsers/framework_packs/models.py`
- Test: `tests/unit/parsers/test_framework_packs.py`
- Test: `tests/unit/tools/test_parser_support_maturity.py`
- Docs: `docs/docs/contributing-language-support.md`

- [x] **Step 1: Write failing validation tests**

```python
def test_load_framework_pack_specs_rejects_unknown_strategy(tmp_path: Path) -> None:
    errors = validate_framework_pack_specs(tmp_path)
    assert "unknown strategy" in errors[0]
```

- [x] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_framework_packs.py -q`
Expected: FAIL because framework-pack validation does not exist yet.

- [x] **Step 3: Implement validation helpers**

```python
def validate_framework_pack_specs(root: Path | None = None) -> list[str]:
    specs = load_framework_pack_specs(root)
    return _validate_specs(specs)
```

- [x] **Step 4: Re-run focused tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_framework_packs.py tests/unit/tools/test_parser_support_maturity.py -q`
Expected: PASS

- [x] **Step 5: Update contributor docs**

Document required fields, supported strategies, package-data expectations, and validation commands for framework-pack YAML.

- [x] **Step 6: Commit**

```bash
git add src/platform_context_graph/parsers/framework_packs docs/docs/contributing-language-support.md tests/unit/parsers/test_framework_packs.py tests/unit/tools/test_parser_support_maturity.py
git commit -m "feat(parsers): validate framework pack specs"
```

## Chunk 2: Node HTTP Framework Lane

Status: completed on this branch with parser facts, file-node persistence, query/story/investigation surfacing, and real repo smoke validation.

### Task 2: Introduce Hapi and Express pack strategies

**Files:**
- Create: `src/platform_context_graph/parsers/framework_packs/specs/hapi.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/specs/express.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/strategies/__init__.py`
- Create: `src/platform_context_graph/parsers/framework_packs/strategies/node_http.py`
- Modify: `src/platform_context_graph/parsers/framework_semantics.py`
- Modify: `src/platform_context_graph/parsers/framework_packs/models.py`
- Test: `tests/unit/parsers/test_javascript_parser.py`
- Test: `tests/unit/parsers/test_typescript_parser.py`
- Test: `tests/unit/parsers/test_framework_packs.py`

- [x] **Step 1: Write failing parser tests for Hapi and Express route modules**

```python
def test_parse_javascript_hapi_route_semantics(...) -> None:
    assert semantics["frameworks"] == ["hapi"]
    assert semantics["hapi"]["route_methods"] == ["GET"]
```

- [x] **Step 2: Run the failing parser tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_javascript_parser.py tests/unit/parsers/test_typescript_parser.py -q`
Expected: FAIL because Hapi/Express semantics are not yet emitted.

- [x] **Step 3: Implement a bounded Node HTTP strategy**

Emit only bounded file-level facts:

```python
{
    "route_methods": ["GET", "POST"],
    "route_paths": ["/health", "/search"],
    "server_symbols": ["server", "app"],
}
```

- [x] **Step 4: Re-run parser tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_javascript_parser.py tests/unit/parsers/test_typescript_parser.py tests/unit/parsers/test_framework_packs.py -q`
Expected: PASS

### Task 3: Persist and surface Node HTTP framework facts

**Files:**
- Modify: `src/platform_context_graph/graph/persistence/file_nodes.py`
- Modify: `src/platform_context_graph/resolution/projection/files.py`
- Modify: `src/platform_context_graph/graph/persistence/files.py`
- Modify: `src/platform_context_graph/query/repositories/framework_summary.py`
- Modify: `src/platform_context_graph/query/story_frameworks.py`
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Test: `tests/unit/core/test_graph_builder_file_framework_semantics.py`
- Test: `tests/unit/resolution/test_fact_projection_file_framework_semantics.py`
- Test: `tests/unit/query/test_repository_framework_summary.py`
- Test: `tests/unit/query/test_story_frameworks.py`

- [x] **Step 1: Write failing persistence/query tests**

```python
assert params["node_http_framework"] == "hapi"
assert summary["hapi"]["route_module_count"] == 3
```

- [x] **Step 2: Run the failing tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py -q`
Expected: FAIL because new node-http fields are not persisted or summarized.

- [x] **Step 3: Add file-node properties and summary logic**

Persist bounded fields only:

- `express_route_methods`
- `express_route_paths`
- `express_server_symbols`
- `hapi_route_methods`
- `hapi_route_paths`
- `hapi_server_symbols`

- [x] **Step 4: Re-run persistence/query tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/resolution/test_fact_projection_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py -q`
Expected: PASS

### Task 4: Run real repo validation for the Node HTTP lane

**Files:**
- Modify: `scripts/validate_language_support_e2e.py`
- Test: `tests/unit/scripts/test_validate_language_support_e2e.py`
- Docs: `docs/superpowers/plans/2026-04-07-language-and-framework-parser-maturity-implementation.md`

- [x] **Step 1: Extend validator expectations for node-http evidence**
No script change was required because the existing framework-evidence validation is generic across framework summaries and story sections.

- [x] **Step 2: Validate real repos**

Run:

```bash
PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/api-node-search-api \
  --language javascript \
  --check \
  --require-framework-evidence

PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/api-node-datastore \
  --language javascript \
  --check \
  --require-framework-evidence

PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/portal-react-platform \
  --language javascript \
  --check \
  --require-framework-evidence
```

Expected: PASS with surfaced Hapi or Express framework evidence where present.

- [ ] **Step 3: Commit**

```bash
git add src/platform_context_graph/parsers/framework_packs src/platform_context_graph/parsers/framework_semantics.py src/platform_context_graph/graph/persistence/file_nodes.py src/platform_context_graph/resolution/projection/files.py src/platform_context_graph/query/repositories/framework_summary.py src/platform_context_graph/query/story_frameworks.py scripts/validate_language_support_e2e.py tests/unit/parsers/test_javascript_parser.py tests/unit/parsers/test_typescript_parser.py tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/resolution/test_fact_projection_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py tests/unit/scripts/test_validate_language_support_e2e.py
git commit -m "feat(parsers): add node framework packs"
```

## Chunk 3: Python Web Framework Lane

### Task 5: Add FastAPI and Flask framework packs

**Files:**
- Create: `src/platform_context_graph/parsers/framework_packs/specs/fastapi.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/specs/flask.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/strategies/python_web.py`
- Modify: `src/platform_context_graph/parsers/framework_semantics.py`
- Modify: `src/platform_context_graph/parsers/languages/python_support.py`
- Test: `tests/unit/parsers/test_python_parser.py`
- Test: `tests/unit/parsers/test_framework_packs.py`

- [ ] **Step 1: Write failing Python parser tests**

```python
def test_parse_python_fastapi_route_semantics(...) -> None:
    assert semantics["frameworks"] == ["fastapi"]
    assert semantics["fastapi"]["route_methods"] == ["GET"]
```

- [ ] **Step 2: Run the failing tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_python_parser.py tests/unit/parsers/test_framework_packs.py -q`
Expected: FAIL because Python framework semantics are not emitted yet.

- [ ] **Step 3: Implement bounded Python web facts**

Emit only:

- `route_methods`
- `route_paths`
- `app_symbols`
- `handler_names`

- [ ] **Step 4: Re-run parser tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_python_parser.py tests/unit/parsers/test_framework_packs.py -q`
Expected: PASS

### Task 6: Persist and surface Python framework facts

**Files:**
- Modify: `src/platform_context_graph/graph/persistence/file_nodes.py`
- Modify: `src/platform_context_graph/resolution/projection/files.py`
- Modify: `src/platform_context_graph/query/repositories/framework_summary.py`
- Modify: `src/platform_context_graph/query/story_frameworks.py`
- Modify: `src/platform_context_graph/query/repositories/context_data.py`
- Test: `tests/unit/core/test_graph_builder_file_framework_semantics.py`
- Test: `tests/unit/query/test_repository_framework_summary.py`
- Test: `tests/unit/query/test_story_frameworks.py`

- [ ] **Step 1: Write failing persistence/query tests for FastAPI and Flask**
- [ ] **Step 2: Run the failing tests**
- [ ] **Step 3: Add bounded file-node properties and summary text**
- [ ] **Step 4: Re-run the focused tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py -q`
Expected: PASS

### Task 7: Run real repo validation for the Python lane

**Files:**
- Modify: `scripts/validate_language_support_e2e.py`
- Test: `tests/unit/scripts/test_validate_language_support_e2e.py`
- Docs: `docs/superpowers/plans/2026-04-07-language-and-framework-parser-maturity-implementation.md`

- [ ] **Step 1: Extend validator expectations for Python web evidence**
- [ ] **Step 2: Validate real repos**

Run:

```bash
PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/recos-ranker-service \
  --language python \
  --check \
  --require-framework-evidence

PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/lambda-python-lb-s3-files \
  --language python \
  --check \
  --require-framework-evidence

PYTHONPATH=src uv run python scripts/validate_language_support_e2e.py \
  --repo-path /Users/allen/repos/services/lambda-python-s3-proxy \
  --language python \
  --check \
  --require-framework-evidence
```

Expected: PASS with FastAPI or Flask evidence where present.

- [ ] **Step 3: Commit**

```bash
git add src/platform_context_graph/parsers/framework_packs src/platform_context_graph/parsers/framework_semantics.py src/platform_context_graph/parsers/languages/python_support.py src/platform_context_graph/graph/persistence/file_nodes.py src/platform_context_graph/resolution/projection/files.py src/platform_context_graph/query/repositories/framework_summary.py src/platform_context_graph/query/story_frameworks.py scripts/validate_language_support_e2e.py tests/unit/parsers/test_python_parser.py tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py tests/unit/scripts/test_validate_language_support_e2e.py
git commit -m "feat(parsers): add python framework packs"
```

## Chunk 4: JS/TS Provider Pack Foundation

### Task 8: Add provider-pack strategy groundwork

**Files:**
- Create: `src/platform_context_graph/parsers/framework_packs/specs/aws_js.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/specs/gcp_js.yaml`
- Create: `src/platform_context_graph/parsers/framework_packs/strategies/provider_calls.py`
- Modify: `src/platform_context_graph/parsers/framework_packs/models.py`
- Modify: `src/platform_context_graph/parsers/framework_semantics.py`
- Test: `tests/unit/parsers/test_javascript_parser.py`
- Test: `tests/unit/parsers/test_typescript_parser.py`
- Test: `tests/unit/parsers/test_framework_packs.py`

- [ ] **Step 1: Write failing provider-pack tests for import + constructor evidence**
- [ ] **Step 2: Run the failing tests**
- [ ] **Step 3: Implement bounded provider facts**

Example:

```python
{
    "providers": ["aws"],
    "services": ["s3", "dynamodb"],
    "client_symbols": ["S3Client"],
}
```

- [ ] **Step 4: Re-run focused tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_javascript_parser.py tests/unit/parsers/test_typescript_parser.py tests/unit/parsers/test_framework_packs.py -q`
Expected: PASS

### Task 9: Decide first graph/query surface for provider facts

**Files:**
- Modify: `src/platform_context_graph/graph/persistence/file_nodes.py`
- Modify: `src/platform_context_graph/query/repositories/framework_summary.py`
- Modify: `src/platform_context_graph/query/story_frameworks.py`
- Test: `tests/unit/query/test_repository_framework_summary.py`
- Docs: `docs/superpowers/specs/2026-04-07-language-and-framework-parser-maturity-design.md`

- [ ] **Step 1: Keep provider surfacing bounded at file/repo summary level**
- [ ] **Step 2: Add failing summary tests**
- [ ] **Step 3: Implement minimal summary fields**
- [ ] **Step 4: Re-run the query tests**

Run: `PYTHONPATH=src uv run python -m pytest tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py -q`
Expected: PASS

## Chunk 5: Framework-Pack Docs and Branch Exit Criteria

### Task 10: Publish framework-pack support docs and completion criteria

**Files:**
- Create: `docs/docs/frameworks/README.md`
- Create: `docs/docs/frameworks/support-maturity.md`
- Modify: `docs/docs/contributing-language-support.md`
- Modify: `docs/superpowers/plans/2026-04-07-language-and-framework-parser-maturity-implementation.md`
- Modify: `scripts/generate_language_capability_docs.py` or create `scripts/generate_framework_pack_docs.py`
- Test: `tests/integration/docs/test_language_capability_docs.py`

- [ ] **Step 1: Decide whether framework docs should be generated alongside language docs**
- [ ] **Step 2: Add failing doc-generation or doc-contract test**
- [ ] **Step 3: Implement doc generation or checked static docs**
- [ ] **Step 4: Re-run doc checks**

Run:

```bash
PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py --check
PYTHONPATH=src uv run python -m pytest tests/integration/docs/test_language_capability_docs.py -q
```

Expected: PASS

### Task 11: Branch wrap-up validation

**Files:**
- Modify: `docs/superpowers/plans/2026-04-07-language-and-framework-parser-maturity-implementation.md`
- Modify: PR description when the branch is ready

- [ ] **Step 1: Run the final branch validation bundle**

Run:

```bash
PYTHONPATH=src uv run python -m pytest tests/unit/parsers/test_framework_packs.py tests/unit/parsers/test_javascript_parser.py tests/unit/parsers/test_typescript_parser.py tests/unit/parsers/test_typescriptjsx_parser.py tests/unit/parsers/test_python_parser.py tests/unit/core/test_graph_builder_file_framework_semantics.py tests/unit/resolution/test_fact_projection_file_framework_semantics.py tests/unit/query/test_repository_framework_summary.py tests/unit/query/test_story_frameworks.py tests/unit/query/test_repository_context_framework_surface.py tests/unit/query/test_investigation_framework_surface.py tests/unit/scripts/test_validate_language_support_e2e.py -q
python3 scripts/check_python_file_lengths.py
python3 scripts/check_python_docstrings.py
git diff --check
uv build
```

Expected: PASS

- [ ] **Step 2: Run final real-repo validations**

Run the validator against at least:

- `/Users/allen/repos/services/portal-nextjs-platform`
- `/Users/allen/repos/services/portal-react-platform`
- `/Users/allen/repos/services/api-node-search-api`
- `/Users/allen/repos/services/recos-ranker-service`

- [ ] **Step 3: Update the PR description**

Include:

- completed React/Next.js declarative pack refactor
- Node HTTP framework lane evidence
- Python framework lane evidence
- provider-pack groundwork
- explicit remaining follow-ups after this branch

---

## Total Remaining After This Plan

If every chunk above is complete, the broader PRD still has follow-on work:

1. extend provider packs beyond the first AWS/GCP slice
2. add deeper TS framework lanes such as NestJS or Remix if local repos justify them
3. add Django or other Python frameworks when we have strong local validation targets
4. carry the same pattern into Go, Java, C#, Ruby, and other supported languages where framework semantics materially matter

Plan complete and saved to `docs/superpowers/plans/2026-04-08-framework-pack-expansion-implementation.md`. Ready to execute?
