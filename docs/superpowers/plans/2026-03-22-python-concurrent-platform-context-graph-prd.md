# Python-First Concurrent PlatformContextGraph PRD Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the remaining PRD work needed to make PlatformContextGraph a Python-first, multi-repo, dual-scope system with workspace-aware runtime parity and bounded-memory watch behavior.

**Architecture:** Keep the current Python coordinator, runtime ingester, PostgreSQL content store, and graph backends. Extend the existing runtime discovery contract into the public CLI through workspace-oriented commands, then finish the remaining repo-partitioned watch, shared indexing, status, and verification work without introducing a new storage engine or language rewrite.

**Tech Stack:** Python, Typer, FastAPI, Neo4j/FalkorDB/KuzuDB, PostgreSQL, pytest, Rich

---

## Current Branch State

These items are already implemented in this worktree and do not need to be redone:

- [x] Bounded concurrent repo parsing in the indexing coordinator
- [x] `pcg index-status` plus API and MCP status surfaces
- [x] Scope-aware code queries with `repo|workspace|ecosystem|auto`
- [x] Auto-scope `pcg watch` with repo-partitioned watch targets and filters
- [x] Stable managed-workspace checkout naming for `org/repo`

The tasks below are the remaining PRD work.

## Chunk 1: Public Workspace Source Parity

### Task 1: Add public `pcg workspace plan|sync|status` commands backed by the runtime ingester contract

**Files:**
- Create: `src/platform_context_graph/cli/helpers/workspace.py`
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Modify: `src/platform_context_graph/cli/main.py`
- Modify: `src/platform_context_graph/runtime/ingester/__init__.py`
- Modify: `src/platform_context_graph/runtime/ingester/git.py`
- Modify: `docs/docs/reference/configuration.md`
- Test: `tests/integration/cli/test_cli_commands.py`
- Test: `tests/unit/runtime/test_repo_sync_rules.py`
- Create: `tests/unit/cli/test_workspace_helper.py`

- [x] **Step 1: Write the failing tests**
Add coverage for:
  - `pcg workspace plan` showing source mode, selected repo count, matched repo IDs, and unmanaged stale checkout count
  - `pcg workspace sync` delegating to the existing repo-sync runtime entrypoint with `RepoSyncConfig.from_env(...)`
  - `pcg workspace status` reporting the configured source mode, workspace path, and latest index/run summary without indexing

- [x] **Step 2: Run the focused red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/integration/cli/test_cli_commands.py tests/unit/cli/test_workspace_helper.py`
Expected: FAIL because the public `workspace` group and helper module do not exist yet.

- [x] **Step 3: Implement the minimal workspace command surface**
Add one focused helper module that:
  - reads `RepoSyncConfig` from the environment
  - reuses runtime discovery helpers instead of duplicating GitHub or filesystem selection logic
  - formats plan/status output for humans while keeping `sync` delegated to the existing runtime entrypoints
  - keeps `explicit` as exact IDs only and leaves regex-over-org behavior under `githubOrg + PCG_REPOSITORY_RULES_JSON`

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/integration/cli/test_cli_commands.py tests/unit/cli/test_workspace_helper.py`
Expected: PASS.

### Task 2: Document the canonical workspace source model

**Files:**
- Modify: `docs/docs/reference/configuration.md`
- Modify: `src/platform_context_graph/runtime/ingester/README.md`
- Test: `tests/integration/cli/test_cli_commands.py`

- [x] **Step 1: Extend the red tests or assertions for help/config text**
Require that help text and docs reflect:
  - `githubOrg|explicit|filesystem`
  - `PCG_REPOSITORY_RULES_JSON` as the canonical selector
  - path-first `pcg index/watch` remaining convenience wrappers for local filesystems

- [x] **Step 2: Run the focused docs/CLI suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/integration/cli/test_cli_commands.py`
Expected: FAIL if new help text is not wired yet.

- [x] **Step 3: Update docs and help text**
Keep the public wording aligned with the actual runtime behavior and avoid promising that `pcg watch` can directly watch GitHub without a local workspace.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/integration/cli/test_cli_commands.py`
Expected: PASS.

## Chunk 2: Public Workspace Execution Parity

### Task 3: Add public `pcg workspace index` on top of the shared coordinator

**Files:**
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Modify: `src/platform_context_graph/cli/helpers/workspace.py`
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Test: `tests/unit/cli/test_indexing_helper.py`
- Test: `tests/integration/cli/test_cli_commands.py`

- [x] **Step 1: Add failing tests for `pcg workspace index`**
Require:
  - it indexes `PCG_REPOS_DIR`
  - it reports repo-aware status instead of treating the workspace as one opaque path
  - it uses the same coordinator-backed helper path as manual indexing

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_indexing_helper.py tests/integration/cli/test_cli_commands.py`
Expected: FAIL before the command exists.

- [x] **Step 3: Implement the minimal command**
Route the public workspace index command through the existing indexing helper and shared coordinator semantics.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_indexing_helper.py tests/integration/cli/test_cli_commands.py`
Expected: PASS.

### Task 4: Add public `pcg workspace watch` with optional rediscovery cadence

**Files:**
- Modify: `src/platform_context_graph/cli/helpers/watch.py`
- Modify: `src/platform_context_graph/cli/helpers/workspace.py`
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Modify: `src/platform_context_graph/core/watcher.py`
- Test: `tests/unit/cli/test_watch_helper.py`
- Test: `tests/unit/core/test_watcher.py`
- Test: `tests/integration/cli/test_cli_commands.py`

- [x] **Step 1: Add failing watch tests**
Require:
  - `pcg workspace watch` watches the local materialized workspace
  - repo include/exclude filters still apply
  - optional rediscovery only affects newly matching repos, not unrelated existing watchers

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_watch_helper.py tests/unit/core/test_watcher.py tests/integration/cli/test_cli_commands.py`
Expected: FAIL before the public workspace watch command and rediscovery hooks exist.

- [x] **Step 3: Implement the minimal workspace watch path**
Keep watch local-only, but allow workspace watch to refresh repo membership on a bounded cadence and preserve repo-partitioned invalidation.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_watch_helper.py tests/unit/core/test_watcher.py tests/integration/cli/test_cli_commands.py`
Expected: PASS.

## Chunk 3: Runtime and Indexing Contract Cleanup

### Task 5: Keep runtime and manual indexing on one repo-partitioned execution model

**Files:**
- Modify: `src/platform_context_graph/indexing/coordinator.py`
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Modify: `src/platform_context_graph/runtime/ingester/bootstrap.py`
- Modify: `src/platform_context_graph/runtime/ingester/sync.py`
- Modify: `src/platform_context_graph/tools/graph_builder_indexing_execution.py`
- Test: `tests/unit/indexing/test_coordinator_execution.py`
- Test: `tests/unit/runtime/test_repo_sync_runtime.py`
- Test: `tests/unit/cli/test_indexing_helper.py`

- [x] **Step 1: Add failing convergence tests**
Require:
  - manual and runtime indexing publish the same repo-level status semantics
  - runtime cycles only reindex changed or newly synced repos
  - `commit_incomplete` repositories resume correctly without a full workspace rerun

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/indexing/test_coordinator_execution.py tests/unit/runtime/test_repo_sync_runtime.py tests/unit/cli/test_indexing_helper.py`
Expected: FAIL where runtime/manual paths still drift.

- [x] **Step 3: Implement the minimal convergence changes**
Keep the coordinator as the single execution engine and narrow any remaining workspace-wide rerun behavior to repo-partitioned worklists.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/indexing/test_coordinator_execution.py tests/unit/runtime/test_repo_sync_runtime.py tests/unit/cli/test_indexing_helper.py`
Expected: PASS.

### Task 6: Tighten the graph-store adapter contract without changing the content-store design

**Files:**
- Modify: `src/platform_context_graph/core/database.py`
- Modify: `src/platform_context_graph/indexing/coordinator_storage.py`
- Modify: `src/platform_context_graph/tools/graph_builder_schema.py`
- Test: `tests/unit/indexing/test_coordinator_storage.py`

- [x] **Step 1: Add failing adapter-conformance tests**
Require:
  - schema init, delete, and capability checks are exercised through one narrow contract
  - backend-specific branching stays out of coordinator hot paths

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/indexing/test_coordinator_storage.py`
Expected: FAIL before the adapter contract is tightened.

- [x] **Step 3: Implement the minimal adapter cleanup**
Do not remove PostgreSQL or change content retrieval contracts. Only narrow the graph-store interface used by indexing and schema setup.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/indexing/test_coordinator_storage.py`
Expected: PASS.

## Chunk 4: UX, Status, and Config Polish

### Task 7: Keep search and status surfaces repo-aware across all scopes

**Files:**
- Modify: `src/platform_context_graph/query/code.py`
- Modify: `src/platform_context_graph/api/routers/code.py`
- Modify: `src/platform_context_graph/mcp/server.py`
- Modify: `src/platform_context_graph/cli/helpers/indexing.py`
- Test: `tests/unit/query/test_code_queries.py`
- Test: `tests/integration/api/test_code_api.py`
- Test: `tests/integration/mcp/test_mcp_server.py`

- [x] **Step 1: Add failing repo-identity assertions**
Require:
  - workspace and ecosystem results always include repo identity
  - `auto` scope selects `repo` when repository context is resolvable
  - CLI/API/MCP status and search outputs stay consistent

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/query/test_code_queries.py tests/integration/api/test_code_api.py tests/integration/mcp/test_mcp_server.py`
Expected: FAIL where repo-aware output is incomplete.

- [x] **Step 3: Implement the minimal output polish**
Prefer output shaping and status consistency over new query features.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/query/test_code_queries.py tests/integration/api/test_code_api.py tests/integration/mcp/test_mcp_server.py`
Expected: PASS.

### Task 8: Expose worker and watch controls as real public configuration

**Files:**
- Modify: `src/platform_context_graph/cli/config_manager.py`
- Modify: `docs/docs/reference/configuration.md`
- Test: `tests/unit/cli/test_indexing_helper.py`
- Test: `tests/unit/cli/test_watch_helper.py`

- [x] **Step 1: Add failing config-surface assertions**
Require:
  - parse workers, queue depth, and watch debounce settings are documented and discoverable
  - legacy `PARALLEL_WORKERS` behavior remains backward-compatible but clearly secondary

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_indexing_helper.py tests/unit/cli/test_watch_helper.py`
Expected: FAIL where config/help output still treats worker settings as opaque.

- [x] **Step 3: Implement config and docs cleanup**
Keep the environment model explicit and aligned with the commands that consume it.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_indexing_helper.py tests/unit/cli/test_watch_helper.py`
Expected: PASS.

## Chunk 5: Verification, Soak, and Benchmark Gates

### Task 9: Add targeted workspace and watch soak coverage

**Files:**
- Modify: `tests/unit/core/test_watcher.py`
- Modify: `tests/unit/runtime/test_repo_sync_runtime.py`
- Create: `tests/integration/runtime/test_workspace_watch_runtime.py`

- [x] **Step 1: Add failing soak-style tests**
Cover:
  - repeated edits across multiple repos in one workspace
  - rediscovery of newly added matching repos
  - unrelated repo changes not forcing whole-workspace refresh

- [x] **Step 2: Run the red suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/core/test_watcher.py tests/unit/runtime/test_repo_sync_runtime.py tests/integration/runtime/test_workspace_watch_runtime.py`
Expected: FAIL before the remaining membership-refresh gaps are closed.

- [x] **Step 3: Implement the minimal soak fixes**
Prefer bounded state, repo partitioning, and deterministic cleanup over feature expansion.

- [x] **Step 4: Re-run the focused suite**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/core/test_watcher.py tests/unit/runtime/test_repo_sync_runtime.py tests/integration/runtime/test_workspace_watch_runtime.py`
Expected: PASS.

### Task 10: Run the PRD verification gates and record remaining risk

**Files:**
- Modify: `docs/superpowers/plans/2026-03-22-python-concurrent-platform-context-graph-prd.md`
- Modify: `docs/docs/reference/configuration.md`

- [x] **Step 1: Run the focused and broad verification commands**
Run:
  - `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_workspace_helper.py tests/unit/cli/test_watch_helper.py tests/unit/core/test_watcher.py tests/unit/indexing/test_coordinator_execution.py tests/unit/indexing/test_coordinator_storage.py tests/unit/query/test_code_queries.py tests/unit/runtime/test_git_checkout_naming.py tests/unit/runtime/test_repo_sync_rules.py tests/unit/runtime/test_repo_sync_runtime.py tests/integration/api/test_api_app.py tests/integration/api/test_code_api.py tests/integration/cli/test_cli_commands.py tests/integration/mcp/test_mcp_server.py`

- [x] **Step 2: Run benchmark and smoke commands**
Run the smallest practical workspace smoke and benchmark commands available in this repo for:
  - one repo
  - a multi-repo workspace
  - watch on a multi-repo workspace

- [x] **Step 3: Record evidence and gaps**
Update this plan or an adjacent status note with:
  - what passed
  - what remains unverified
  - the next escalation if Python misses the PRD benchmark gates

#### Verification evidence

- `PYTHONPATH=src uv run pytest -q tests/unit/cli/test_workspace_helper.py tests/unit/cli/test_watch_helper.py tests/unit/core/test_watcher.py tests/unit/indexing/test_coordinator_execution.py tests/unit/indexing/test_coordinator_storage.py tests/unit/query/test_code_queries.py tests/unit/runtime/test_git_checkout_naming.py tests/unit/runtime/test_repo_sync_rules.py tests/unit/runtime/test_repo_sync_runtime.py tests/integration/api/test_api_app.py tests/integration/api/test_code_api.py tests/integration/cli/test_cli_commands.py tests/integration/mcp/test_mcp_server.py tests/integration/runtime/test_workspace_watch_runtime.py`
  - result: `126 passed`
- `PYTHONPATH=src uv run pytest -q tests/perf/test_large_indexing.py`
  - result: `1 passed`
- `PYTHONPATH=src PCG_REPO_SOURCE_MODE=filesystem PCG_FILESYSTEM_ROOT="$PWD/tests/fixtures/sample_projects" PCG_REPOS_DIR="$TMPDIR/.../repos" uv run pcg workspace plan`
  - result: succeeded, `20` repositories discovered from the fixture workspace
- `PYTHONPATH=src PCG_REPO_SOURCE_MODE=filesystem PCG_FILESYSTEM_ROOT="$PWD/tests/fixtures/sample_projects" PCG_REPOS_DIR="$TMPDIR/.../repos" uv run pcg workspace sync`
  - result: succeeded, `discovered=20 cloned=20 updated=0 skipped=0 failed=0 stale=0`
- `PYTHONPATH=src uv run pytest -q tests/integration/runtime/test_workspace_watch_runtime.py`
  - result: `1 passed`
- `docker-compose run --rm --no-deps -v /Users/allen/personal-repos/platform-context-graph/.worktrees/python-concurrent-platform-context-graph:/work -w /work -e PYTHONPATH=/work/src -e DEFAULT_DATABASE=neo4j -e NEO4J_URI=bolt://neo4j:7687 -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=testpassword -e PCG_CONTENT_STORE_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_POSTGRES_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_GIT_AUTH_METHOD=none bootstrap-index sh -lc 'pcg index /work/tests/fixtures/sample_projects/sample_project'`
  - result: succeeded against live compose Neo4j/Postgres, single-repo indexing finished in `6.09s`
- `docker-compose run --rm --no-deps -v /Users/allen/personal-repos/platform-context-graph/.worktrees/python-concurrent-platform-context-graph:/work -w /work -e PYTHONPATH=/work/src -e DEFAULT_DATABASE=neo4j -e NEO4J_URI=bolt://neo4j:7687 -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=testpassword -e PCG_CONTENT_STORE_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_POSTGRES_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_REPO_SOURCE_MODE=filesystem -e PCG_FILESYSTEM_ROOT=/work/tests/fixtures/sample_projects -e PCG_REPOS_DIR=/tmp/pcg-workspace -e PCG_GIT_AUTH_METHOD=none bootstrap-index sh -lc 'pcg workspace sync && pcg workspace index'`
  - result: succeeded against live compose Neo4j/Postgres, workspace sync discovered `20` repos and workspace indexing finished in `38.11s`
- `docker-compose run --rm --no-deps -v /Users/allen/personal-repos/platform-context-graph/.worktrees/python-concurrent-platform-context-graph:/work -w /work -e PYTHONPATH=/work/src -e DEFAULT_DATABASE=neo4j -e NEO4J_URI=bolt://neo4j:7687 -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=testpassword -e PCG_CONTENT_STORE_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_POSTGRES_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_GIT_AUTH_METHOD=none bootstrap-index sh -lc 'python - <<\"PY\" ... pcg watch /tmp/live-watch-workspace --scope workspace ... PY'`
  - result: succeeded against live compose Neo4j/Postgres, watcher started on a two-repo git workspace, completed the initial scan, and shut down cleanly with `watch_returncode=0`
- `docker-compose run --rm --no-deps -v /Users/allen/personal-repos/platform-context-graph/.worktrees/python-concurrent-platform-context-graph:/work -w /work -e PYTHONPATH=/work/src -e DEFAULT_DATABASE=neo4j -e NEO4J_URI=bolt://neo4j:7687 -e NEO4J_USERNAME=neo4j -e NEO4J_PASSWORD=testpassword -e PCG_CONTENT_STORE_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_POSTGRES_DSN=postgresql://pcg:testpassword@postgres:5432/platform_context_graph -e PCG_GIT_AUTH_METHOD=none bootstrap-index sh -lc 'pcg index --force /work/tests/fixtures/sample_projects/sample_project'`
  - result: succeeded against live compose Neo4j/Postgres, `--force` now bypasses the skip gate and re-indexes the repository in `3.02s` without the prior `SOURCES_FROM` warning noise

#### Remaining gaps

- Kùzu-backed CLI smoke is still unverified in this worktree runtime.
  - `PYTHONPATH=src PCG_RUNTIME_DB_TYPE=kuzudb KUZUDB_PATH="$TMPDIR/.../kuzu" uv run pcg index tests/fixtures/sample_projects/sample_project`
  - result: failed before indexing because Kùzu is not installed in this environment
- The only benchmark available in-repo is `tests/perf/test_large_indexing.py`, which measures mocked Python loop overhead, not full end-to-end parse+persist throughput.
- We still do not have a real 100/500/1000-repo benchmark corpus or an 8-hour watch RSS soak in this local environment.

#### Escalation rule

- If a real graph-backend environment still misses the PRD throughput or memory targets after profiling the Python coordinator/watch pipeline, the next escalation remains a separate PRD for a Go-based ingester/watch runtime rather than an in-flight rewrite on this branch.
