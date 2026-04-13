# Go Write Plane Conversion Cutover Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fully remove Python ownership from the current PCG write plane so this branch can merge as a real Go write-plane conversion before any new ingestor work starts.

**Architecture:** keep the Python read plane temporarily if needed, but move all collector, projection, reducer, recovery, and deployed write-runtime ownership to Go. The branch is complete only when the Git write path no longer depends on Python bridges, deployed write services no longer start from Python runtime entrypoints, and the legacy post-commit/finalization seam is deleted instead of documented forever.

**Tech Stack:** Go, PostgreSQL, Neo4j, Docker Compose, Helm, OpenTelemetry, Python only as a shrinking compatibility surface until deletion.

---

## Current Truth

The rewrite proof and documentation package is complete, but the Git write-plane
conversion is not.

The branch still has active Python-owned write-plane seams:

- Python runtime entrypoints still own deployed write roles in
  `src/platform_context_graph/cli/commands/runtime.py`.
- `go/cmd/collector-git/service.go` still imports and depends on
  `go/internal/compatibility/pythonbridge/*`.
- the Git collector still shells into Python bridge modules under
  `src/platform_context_graph/runtime/ingester/go_collector_*bridge.py`.
- recovery and refinalization still depend on Python bridge code in
  `src/platform_context_graph/collectors/git/finalize.py`,
  `src/platform_context_graph/indexing/post_commit_writer.py`, and
  `src/platform_context_graph/api/routers/admin.py`.

No new ingestors should start until the milestones in this plan are complete.
Treat this plan as the active cutover path until the merge bar below is fully
met.

## Merge Bar

This branch is mergeable only when all of the following are true:

- no deployed write service starts from Python runtime entrypoints
- no Go write-plane service imports `go/internal/compatibility/pythonbridge`
- no Python bridge modules under `src/platform_context_graph/runtime/ingester/`
  are required for normal Git ingestion
- no normal recovery or refinalize path depends on Python finalization bridge
  code
- Docker Compose and Helm run the Go-owned write plane
- local and cloud validation prove parity for the Git write path

The Python API, MCP, and query plane may remain for now. The write plane may
not.

No new ingestors before Git cutover completes.

## Chunk 1: Correct The Completion Bar

### Task 1: Re-baseline docs and branch status

**Files:**
- Modify: `docs/superpowers/plans/2026-04-12-go-data-plane-rewrite-sow.md`
- Modify: `docs/docs/adrs/2026-04-12-cutover-and-legacy-bridge.md`
- Modify: `docs/docs/roadmap.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/reference/source-layout.md`
- Modify: `docs/docs/guides/collector-authoring.md`
- Test: `docs/mkdocs.yml`

- [ ] **Step 1: Change the branch language from "rewrite complete" to "rewrite proof complete, conversion incomplete"**

Document that the proof/architecture package is done, but Git write-plane
cutover is still in progress.

- [ ] **Step 2: Add the hard merge bar to the docs**

Document the exact deletion and runtime-ownership conditions from the "Merge
Bar" section above.

- [ ] **Step 3: Add a visible "no new ingestors before Git cutover" rule**

Put that rule in the rewrite SOW, roadmap, and collector authoring guide.

- [ ] **Step 4: Run docs verification**

Run:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-04-12-go-data-plane-rewrite-sow.md \
  docs/docs/adrs/2026-04-12-cutover-and-legacy-bridge.md \
  docs/docs/roadmap.md \
  docs/docs/deployment/service-runtimes.md \
  docs/docs/reference/source-layout.md \
  docs/docs/guides/collector-authoring.md
git commit -m "docs(cutover): mark write-plane conversion incomplete"
```

## Chunk 2: Remove Python From Collector-Git Hot Path

### Task 2: Replace Python repo selection and snapshotting with native Go

**Files:**
- Modify: `go/cmd/collector-git/service.go`
- Delete: `go/cmd/collector-git/source_python_bridge.go`
- Delete: `go/internal/compatibility/pythonbridge/collector_git.go`
- Delete: `go/internal/compatibility/pythonbridge/git_selection.go`
- Delete: `go/internal/compatibility/pythonbridge/snapshot_git.go`
- Delete: `go/internal/compatibility/pythonbridge/collector_git_test.go`
- Delete: `go/internal/compatibility/pythonbridge/git_selection_test.go`
- Delete: `go/internal/compatibility/pythonbridge/snapshot_git_test.go`
- Create: `go/internal/collector/git_selection_native.go`
- Create: `go/internal/collector/git_selection_native_test.go`
- Create: `go/internal/collector/git_snapshot_native.go`
- Create: `go/internal/collector/git_snapshot_native_test.go`
- Modify: `go/internal/collector/git_source.go`
- Modify: `go/internal/collector/git_source_test.go`
- Modify: `go/internal/collector/service_test.go`
- Modify: `go/cmd/collector-git/service_test.go`

- [ ] **Step 1: Write failing Go tests for native repo selection**

Cover repo discovery, filtering, and identity normalization without invoking
Python.

- [ ] **Step 2: Write failing Go tests for native repo snapshot collection**

Cover per-repo snapshot capture, fingerprinting, content facts, and error
paths without invoking Python.

- [ ] **Step 3: Implement native selection**

Move selection behavior into `go/internal/collector/git_selection_native.go`
and wire `collector.GitSource.Selector` to the native implementation.

- [ ] **Step 4: Implement native snapshot collection**

Move snapshot behavior into `go/internal/collector/git_snapshot_native.go` and
wire `collector.GitSource.Snapshotter` to the native implementation.

- [ ] **Step 5: Delete Python bridge imports and code**

Remove all imports of `go/internal/compatibility/pythonbridge` from the
collector runtime and delete the Go bridge package.

- [ ] **Step 6: Delete the Python Git bridge modules**

Delete:

```text
src/platform_context_graph/runtime/ingester/go_collector_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_bridge_facts.py
src/platform_context_graph/runtime/ingester/go_collector_selection_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_snapshot_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_snapshot_collection.py
```

- [ ] **Step 7: Run focused collector verification**

Run:

```bash
cd go && go test ./internal/collector ./cmd/collector-git -count=1
```

Expected: PASS

- [ ] **Step 8: Run the compose collector proof**

Run:

```bash
./scripts/verify_collector_git_runtime_compose.sh
```

Expected: PASS with no Python bridge invocation in the normal collector path

- [ ] **Step 9: Commit**

```bash
git add go/cmd/collector-git \
  go/internal/collector \
  src/platform_context_graph/runtime/ingester
git commit -m "feat(cutover): remove python from collector-git hot path"
```

## Chunk 3: Make Deployed Write Services Actually Go-Owned

### Task 3: Replace Python write-runtime entrypoints in deployable surfaces

**Files:**
- Create: `go/cmd/ingester/main.go`
- Create: `go/cmd/ingester/main_test.go`
- Create: `go/cmd/bootstrap-index/main.go`
- Create: `go/cmd/bootstrap-index/main_test.go`
- Modify: `go/cmd/projector/main.go`
- Modify: `go/cmd/reducer/main.go`
- Modify: `Dockerfile`
- Modify: `docker-compose.yaml`
- Modify: `deploy/helm/platform-context-graph/templates/deployment.yaml`
- Modify: `deploy/helm/platform-context-graph/templates/deployment-resolution-engine.yaml`
- Modify: `deploy/helm/platform-context-graph/templates/statefulset.yaml`
- Modify: `deploy/helm/platform-context-graph/values.yaml`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/deployment/docker-compose.md`
- Modify: `docs/docs/reference/local-testing.md`
- Modify: `docs/docs/reference/cloud-validation.md`

- [ ] **Step 1: Write failing deployment/runtime tests**

Add or update tests so deploy assets fail unless they point at Go-owned write
services rather than Python `pcg internal ...` runtime commands.

- [ ] **Step 2: Add a Go-owned ingester entrypoint**

Create `go/cmd/ingester/main.go` that owns the long-running repo sync loop for
the Git write plane.

- [ ] **Step 3: Add a Go-owned bootstrap indexing entrypoint**

Create `go/cmd/bootstrap-index/main.go` for one-shot write-plane bootstrap,
separate from database bootstrap.

- [ ] **Step 4: Update Docker and deployment assets**

Make Compose and Helm run the Go write binaries for ingester, bootstrap,
projector, and reducer.

- [ ] **Step 5: Keep admin/status, tracing, metrics, and pool tuning intact**

Ensure the deployed write services keep the same operator contract and tunable
connection-pool behavior.

- [ ] **Step 6: Run runtime and deploy verification**

Run:

```bash
cd go && go test ./cmd/ingester ./cmd/bootstrap-index ./cmd/projector ./cmd/reducer ./internal/runtime -count=1
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
helm lint deploy/helm/platform-context-graph
```

Expected: PASS

- [ ] **Step 7: Run full-stack compose proof**

Run:

```bash
docker compose up --build
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/api/v0/index-status
```

Expected: write-plane services are Go-owned, API remains available, and
checkpoint completeness still works

- [ ] **Step 8: Commit**

```bash
git add go/cmd Dockerfile docker-compose.yaml deploy/helm/platform-context-graph \
  docs/docs/deployment docs/docs/reference/local-testing.md docs/docs/reference/cloud-validation.md
git commit -m "feat(cutover): run deployed write services from go"
```

## Chunk 4: Replace Python Recovery And Finalization

### Task 4: Move refinalize and post-commit recovery to Go-owned replay paths

**Files:**
- Modify: `go/internal/projector/runtime.go`
- Modify: `go/internal/projector/service.go`
- Modify: `go/internal/reducer/runtime.go`
- Modify: `go/internal/runtime/admin.go`
- Modify: `go/internal/runtime/status_server.go`
- Modify: `go/internal/storage/postgres/status.go`
- Delete: `src/platform_context_graph/indexing/post_commit_writer.py`
- Delete: `src/platform_context_graph/collectors/git/finalize.py`
- Delete: `src/platform_context_graph/indexing/coordinator_finalize.py`
- Modify: `src/platform_context_graph/api/routers/admin.py`
- Delete: `src/platform_context_graph/cli/helpers/finalize.py`
- Modify: `src/platform_context_graph/cli/commands/basic.py`
- Modify: `docs/docs/adrs/2026-04-12-cutover-and-legacy-bridge.md`
- Modify: `docs/docs/reference/http-api.md`
- Modify: `docs/docs/reference/cli-reference.md`

- [ ] **Step 1: Write failing recovery-path tests**

Cover graph-safe replay, stage-specific recovery, and refinalize status without
calling Python finalization helpers.

- [ ] **Step 2: Add Go-owned replay and recovery handlers**

Implement Go-owned recovery entrypoints in projector/reducer/runtime admin
surfaces.

- [ ] **Step 3: Rewire admin and CLI surfaces**

Make Python admin and CLI surfaces either proxy to Go-owned recovery behavior
or remove the write-plane operation entirely.

- [ ] **Step 4: Delete the Python finalization bridge**

Remove the explicit post-commit writer and finalize bridge files once parity is
proven.

- [ ] **Step 5: Run focused recovery verification**

Run:

```bash
cd go && go test ./internal/projector ./internal/reducer ./internal/runtime ./internal/storage/postgres -count=1
PYTHONPATH=src uv run pytest tests/unit/api/test_admin_router.py tests/integration/api/test_admin_facts_replay.py tests/integration/cli/test_admin_facts_replay_cli.py -q
```

Expected: PASS with no Python finalization bridge remaining in the normal
recovery path

- [ ] **Step 6: Commit**

```bash
git add go/internal/projector go/internal/reducer go/internal/runtime go/internal/storage/postgres \
  src/platform_context_graph/api/routers/admin.py src/platform_context_graph/cli/commands/basic.py
git rm src/platform_context_graph/indexing/post_commit_writer.py \
  src/platform_context_graph/collectors/git/finalize.py \
  src/platform_context_graph/indexing/coordinator_finalize.py \
  src/platform_context_graph/cli/helpers/finalize.py
git commit -m "feat(cutover): replace python finalization and recovery"
```

## Chunk 5: Delete Python Write-Plane Ownership

### Task 5: Remove Python runtime/coordinator ownership from normal write flow

**Files:**
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Modify: `src/platform_context_graph/app/service_entrypoints.py`
- Delete or quarantine: `src/platform_context_graph/runtime/ingester/*`
- Delete or quarantine: `src/platform_context_graph/indexing/*`
- Modify: `docs/docs/reference/source-layout.md`
- Modify: `docs/docs/architecture.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/roadmap.md`

- [ ] **Step 1: Write failing runtime-ownership tests**

Add tests or assertions that fail if normal write-plane deployment still routes
through Python runtime entrypoints.

- [ ] **Step 2: Remove Python write-runtime command ownership**

Make `bootstrap-index`, `repo-sync-loop`, and `resolution-engine` no longer the
normal deployed write-plane commands.

- [ ] **Step 3: Delete or quarantine Python write modules**

Anything left under `src/platform_context_graph/runtime/ingester/` and
`src/platform_context_graph/indexing/` should either be deleted or moved out of
the normal write path with explicit compatibility labeling.

- [ ] **Step 4: Run repo-wide cutover checks**

Run:

```bash
rg -n "pythonbridge" go src
rg -n "go_collector_.*bridge" src/platform_context_graph
rg -n "@internal_app.command\\(\"bootstrap-index|@internal_app.command\\(\"repo-sync-loop|@internal_app.command\\(\"resolution-engine" src/platform_context_graph/cli/commands/runtime.py
```

Expected:

- no normal write-plane dependency on `pythonbridge`
- no live Go collector bridge modules left
- no Python runtime entrypoints still presented as the deployed write plane

- [ ] **Step 5: Run final parity gates**

Run:

```bash
cd go && go test ./... -count=1
PYTHONPATH=src uv run pytest tests/integration/api/test_api_app.py tests/integration/cli/test_remote_cli.py tests/integration/mcp/test_repository_runtime_context.py -q
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

Expected: PASS

- [ ] **Step 6: Cloud parity proof**

Run the cloud test instance proof for one Git write cycle and verify:

- Go ingester writes facts and generations
- Go projector drains source-local work
- Go reducer drains reducer intents
- API still serves canonical reads correctly
- telemetry and admin/status surfaces remain truthful

- [ ] **Step 7: Commit**

```bash
git add go src/platform_context_graph docs
git commit -m "feat(cutover): remove python write-plane ownership"
```

## Remaining Effort

This is not a small cleanup. Relative to the intent of the branch, the
remaining conversion is still large.

Best estimate:

- Chunk 1: Small
- Chunk 2: Large
- Chunk 3: Large
- Chunk 4: Large
- Chunk 5: Large

In plain language: the hardest and most merge-critical part is still ahead,
because it is deletion, ownership flip, and parity proof work rather than
proof-of-concept work.

## Stop Rule

Do not begin AWS, Kubernetes, or any other new ingestor implementation until
Chunks 1 through 5 are complete and the merge bar is satisfied.
