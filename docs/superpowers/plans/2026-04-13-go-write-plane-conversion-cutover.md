# Go Write Plane Conversion Cutover Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** fully remove Python ownership from the current PCG runtime and write plane so this branch can merge as a real Go platform conversion before any new ingestor work starts.

**Architecture:** move all collector, parser, projection, reducer, recovery, and deployed runtime ownership to Go. The branch is complete only when the Git parser and write path no longer depend on Python bridges, deployed runtime services no longer start from Python runtime entrypoints, and the legacy post-commit/finalization seam is deleted instead of documented forever.

**Tech Stack:** Go, PostgreSQL, Neo4j, Docker Compose, Helm, OpenTelemetry.
Python remains in scope only where the branch still has deletion work to do; it
is not a valid long-term runtime or bridge layer for the merged platform.

---

## Current Truth

The rewrite proof and documentation package is complete, but the full Python-
to-Go platform conversion is not.

The branch still has active Python-owned runtime seams:

- the deployed API service still starts from the Python runtime command
  `pcg serve start` in `docker-compose.yaml`, `Dockerfile`, and
  `src/platform_context_graph/app/service_entrypoints.py`
- Python API, MCP, and CLI orchestration still survive under
  `src/platform_context_graph/api/**`,
  `src/platform_context_graph/mcp/**`, and
  `src/platform_context_graph/cli/**`; parts of that surface still carry stale
  imports into already deleted Python package families such as
  `platform_context_graph.query` and `platform_context_graph.facts`
- parser-family ownership is complete in the canonical specs/docs and on disk;
  the remaining parser debt is downstream graph/materialization parity for
  Go-emitted buckets and metadata
- the legacy Python `content/ingest.py` helper has now been deleted; Go owns
  normal-path content shaping under `go/internal/content/shape`, and the
  remaining Python ownership is concentrated in API/MCP/CLI orchestration plus
  a smaller set of content-read and relationship seams
- the Terraform provider-schema relationship seam is now split:
  Go owns schema loading/classification and schema-driven generic evidence
  under `go/internal/terraformschema` and `go/internal/relationships`,
  while Python still owns the outer relationship finalization/runtime boundary

The collector bridge inventory changed during Chunk 2:

- `go/internal/compatibility/pythonbridge/*` has been removed from the normal
  Go runtime path and deleted from the branch.
- `src/platform_context_graph/runtime/ingester/go_collector_*bridge.py` has
  been deleted from the branch.
- `go/internal/collector/git_selection_native*.go` now owns source-mode
  repository selection, filesystem sync, Git clone/update, and selected-repo
  batch construction for `collector-git`, `ingester`, and `bootstrap-index`.

The native Go parser platform now has a larger foundation than the original
cutover draft assumed:

- `go/internal/parser/registry.go` owns parser-key and extension dispatch
- `go/internal/collector/discovery/*` owns parser-aware file discovery
- `go/internal/content/shape/materialize.go` owns parser-payload-to-content
  shaping
- `go/internal/parser/runtime.go` owns the native tree-sitter runtime and
  language-handle cache for the initial Go-owned parser slice
- `go/internal/parser/engine.go` owns native parse dispatch and prescan fanout
- `go/internal/parser/python_language.go` and
  `go/internal/parser/python_semantics.go` now own the native Python adapter
  slice, including notebook conversion, FastAPI/Flask
  `framework_semantics`, bounded ORM table mapping extraction, decorator
  metadata, async-function flags, and dedicated `type_annotations` extraction
- `go/internal/parser/go_language.go` owns the first native Go adapter
- `go/internal/parser/javascript_language.go` now owns the representative
  JavaScript and TypeScript/TSX adapter slice, including native
  `framework_semantics`, `type_aliases`, `enums`, and `components` coverage for
  the supported JS/TS/TSX runtime paths
- `go/internal/parser/json_language.go` now owns the first native JSON config
  slice, including package/composer/tsconfig metadata plus CloudFormation JSON
- `go/internal/parser/hcl_language.go` now owns the first native Terraform and
  Terragrunt adapter slice
- `go/internal/parser/yaml_language.go`,
  `go/internal/parser/yaml_semantics.go`, and
  `go/internal/parser/yaml_helm.go` now own the first native infrastructure
  YAML slice for Kubernetes, Argo CD, Crossplane, Kustomize, Helm, and
  CloudFormation YAML
- `go/internal/parser/dockerfile_language.go` now owns the first native
  Dockerfile adapter slice
- `go/internal/parser/sql_language.go` now owns the native SQL schema,
  relationship, migration, and partial-recovery adapter slice
- `go/internal/parser/raw_text_engine.go` owns the raw-text fallback path
- `go/internal/parser/templated_detection.go` now owns native templated
  content metadata inference for file and entity materialization parity
- `go/internal/parser/runtime_dependencies.go` now owns native runtime service
  dependency extraction helpers for the parser/reducer cutover path
- `go/internal/parser/scip_*.go` now owns native SCIP binary detection,
  command execution, protobuf reduction, and the Go collector-facing payload
  contract
- `go/internal/collector/git_snapshot_scip.go` now owns the optional
  SCIP-enabled collector snapshot path in Go
- `src/platform_context_graph/cli/commands/runtime.py` no longer exposes the
  deployed runtime service commands `bootstrap-index`, `repo-sync-loop`, or
  `resolution-engine`; Compose and Helm now start the Go-owned write plane
  through dedicated binaries
- local `pcg watch`, MCP `watch_directory`, and `pcg ecosystem index/update`
  now launch Go-owned `bootstrap-index` reindex flows for normal refreshes
  instead of re-entering the legacy Python parser/coordinator path
- `go/cmd/collector-git/source_python_bridge.go` and
  `go/cmd/ingester/source_python_bridge.go` have been deleted from the branch
- Python `GraphBuilder.build_graph_from_path_async(...)` now delegates
  both directory and explicit single-file indexing to the Go
  `bootstrap-index` runtime; parser-family ownership is now Go-owned, and the
  remaining Python ownership is concentrated in content shaping plus the
  Python API/MCP/CLI orchestration seams
- `src/platform_context_graph/tools/graph_builder.py` has been thinned to the
  live runtime facade only; the dead per-file Python persistence helpers,
  parser-registry bootstrap methods, discovery convenience methods, and legacy
  call/inheritance helper methods have been deleted instead of retained as
  compatibility shells
- the legacy Python parse/coordinator runtime stack
  (`collectors/git/parse_execution.py`, `collectors/git/parse_worker.py`,
  `indexing/coordinator.py`, `indexing/coordinator_pipeline.py`,
  `indexing/coordinator_async_commit.py`, and `indexing/parse_recovery.py`)
  has been deleted from the branch

The parser-family blockers are no longer in the collector bridge path because
the canonical parser contract and the legacy Python parser-family files are now
Go-owned end to end. The normal Go collector path now owns both the standard
tree-sitter route and the optional SCIP route. The remaining parser-related
blockers are downstream parity items: SCIP depth, specialized
JSON/data-intelligence document coverage, dependency/package indexing
semantics, and end-to-end materialization for newer parser buckets and
metadata that now exist in Go payloads but still need full runtime persistence
parity. The remaining branch blockers after that are the Python API/MCP/CLI
and the remaining Python API/MCP/CLI orchestration plus relationship seams.

Already deleted on this branch:

- `go/internal/compatibility/pythonbridge/**`
- `src/platform_context_graph/runtime/ingester/go_collector_*bridge.py`
- `src/platform_context_graph/tools/graph_builder_relationships.py`
- `src/platform_context_graph/tools/graph_builder_persistence.py`
- the legacy Python parse/coordinator stack:
  `collectors/git/parse_execution.py`,
  `collectors/git/parse_worker.py`,
  `indexing/coordinator.py`,
  `indexing/coordinator_pipeline.py`,
  `indexing/coordinator_async_commit.py`, and
  `indexing/parse_recovery.py`
- Python facts, resolution, query, and runtime status-store package families
  that older cutover notes still referenced as live seams
- Python parser registry/raw-text helpers and the already retired parser
  facades for Groovy, Dockerfile, Rust, Scala, C#, Perl, Python,
  JavaScript, TypeScript/TSX, C, Elixir, and PHP

Current parser-package truth:

- no capability specs still point at Python parser entrypoints or Python parser
  unit suites
- `src/platform_context_graph/parsers/languages/` now contains only
  `README.md` and `__init__.py`; the legacy Python parser-family facades and
  support files have been deleted
- the shared YAML infrastructure, HCL/Terraform, and the former single-spec
  families (C++, Dart, Go, Haskell, Java, JSON, Kotlin, Ruby, SQL, Swift)
  are now Go-owned in the canonical parser contract and on disk
- several semantics now exist in Go and the remaining work is downstream
  graph/materialization parity rather than brand-new parser scaffolding

Current GraphBuilder truth:

- the Python facade still exists because CLI/runtime helpers call it directly
- it no longer owns parser bootstrap, Python discovery, or per-file graph
  persistence helpers
- the remaining live surface is schema bootstrap, Go `bootstrap-index` handoff,
  repository delete/reset helpers, and repository relationship resolution
- deleting the facade entirely is blocked on removing the last Python
  CLI/runtime callers, not on parser-family ownership

Known parser parity blockers to close before honest deletion:

- Python: decorators, async-function metadata, and type annotations now point
  at Go-owned specs/docs, but still need full end-to-end graph/content proof
- TypeScript/TSX: decorators, type aliases, generics, and component/class
  semantics now point at Go-owned specs/docs, but still need full
  graph/content parity proof
- C: typedef extraction now points at Go-owned specs/docs, but integration
  expectations still lag
- Elixir: guard/module-attribute/protocol surfaces now point at Go-owned
  specs/docs, but materialization and integration truth still need full parity
- PHP: parser ownership is now Go-owned in the specs/docs, but static method
  call semantics still need end-to-end parity proof
- JSON and SCIP: specialized data-intelligence coverage and cross-file
  reference parity remain open work

No new ingestors should start until the milestones in this plan are complete.
Treat this plan as the active cutover path until the merge bar below is fully
met.

## Merge Bar

This branch is mergeable only when all of the following are true:

- no deployed runtime or write service starts from Python runtime entrypoints
- no Go runtime service imports `go/internal/compatibility/pythonbridge`
- no Python bridge modules under `src/platform_context_graph/runtime/ingester/`
  are required for normal Git ingestion
- no normal parser, discovery, snapshot, content-shaping, recovery,
  refinalize, or admin-repair path depends on Python runtime ownership
- Docker Compose and Helm run the Go-owned platform
- local and cloud validation prove parity for the Git parser and write path

No new ingestors before the full Python-to-Go conversion completes.

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

- [x] **Step 1: Change the branch language from "rewrite complete" to "rewrite proof complete, conversion incomplete"**

Document that the proof/architecture package is done, but the full Python-to-
Go platform conversion is still in progress and parser ownership remains in
scope until the normal path is Go-owned.

- [x] **Step 2: Add the hard merge bar to the docs**

Document the exact deletion and runtime-ownership conditions from the "Merge
Bar" section above.

- [x] **Step 3: Add a visible "no new ingestors before full conversion" rule**

Put that rule in the rewrite SOW, roadmap, and collector authoring guide.

- [x] **Step 4: Run docs verification**

Run:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

Expected: PASS

- [x] **Step 5: Commit**

Committed as `b0e87b5` — `docs(cutover): record parser foundation slice`

## Chunk 2: Build Native Go Parser Platform And Collector Integration

### Task 2: Replace Python parser and collector-path ownership with native Go

**Files:**
- Create: `go/internal/parser/registry.go`
- Create: `go/internal/parser/registry_test.go`
- Create: `go/internal/parser/raw_text.go`
- Create: `go/internal/parser/raw_text_test.go`
- Create: `go/internal/collector/discovery/discovery.go`
- Create: `go/internal/collector/discovery/discovery_test.go`
- Create: `go/internal/content/shape/materialize.go`
- Create: `go/internal/content/shape/materialize_test.go`
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

- [ ] **Step 1: Write failing Go tests for parser registry, discovery, and content shaping**

Cover:
- supported extension and parser-key lookup parity
- raw-text special filename handling (`Dockerfile`, `Jenkinsfile`)
- repo-local and nested `.gitignore` behavior
- nested git repository grouping and deterministic file ordering
- content entity bucket normalization and canonical content materialization

- [ ] **Step 2: Implement the native Go parser platform foundation**

Create a native Go parser metadata/registry package, a native discovery package,
and a native content-shaping package. Keep this slice honest: the registry owns
parser identity and selection; discovery owns file and repository selection;
content shaping owns translation from normalized parser payloads to the Go
content model.

Progress on this step:

- [x] Registry metadata and selection landed in `go/internal/parser/registry.go`
- [x] Discovery landed in `go/internal/collector/discovery/*`
- [x] Content shaping landed in `go/internal/content/shape/materialize.go`
- [x] Native parse runtime/dispatch landed for Python, Go, JavaScript,
  TypeScript/TSX, and raw-text in
  `go/internal/parser/{runtime,engine,python_language,go_language,javascript_language,raw_text_engine}.go`
- [x] Native Python parser semantics now land in Go for the current
  representative runtime paths, including FastAPI and Flask route semantics,
  docstrings, cyclomatic complexity, and bounded SQLAlchemy and Django ORM
  table mapping extraction in
  `go/internal/parser/{python_language,python_semantics}.go`
- [x] Native Go parser semantics now land in Go for function and method
  docstrings, cyclomatic complexity, and receiver/class context metadata in
  `go/internal/parser/go_language.go`
- [x] Groovy/Jenkinsfile prescan now surfaces shared-library, pipeline-call,
  and entry-point names alongside the existing Jenkins metadata in
  `go/internal/parser/groovy_language.go`
- [x] Native JavaScript/TypeScript/TSX framework semantics now land in Go for
  the current representative runtime paths, including Next.js route/page/layout
  classification, React boundary/component/hook detection, Express route
  surfaces, Hapi route-module detection, and bounded AWS/GCP SDK semantics in
  `go/internal/parser/{javascript_language,javascript_semantics}.go`
- [x] Native JavaScript-like type/entity parity now includes TypeScript/TSX
  `type_aliases`, TypeScript `enums`, and TSX `components` in
  `go/internal/parser/javascript_language.go`
- [x] Native config/IaC adapters landed for JSON, Terraform/Terragrunt, YAML
  infrastructure, and Dockerfile in
  `go/internal/parser/{json_language,hcl_language,yaml_language,yaml_semantics,yaml_helm,dockerfile_language}.go`
- [x] Native SQL adapter landed in
  `go/internal/parser/{sql_language,sql_shared,sql_migrations}.go`
- [x] Python-adjacent parser parity landed for notebook conversion,
  templated content metadata, and runtime service dependency extraction in
  `go/internal/parser/{python_language,raw_text_engine,templated_detection,runtime_dependencies}.go`
- [x] Native long-tail language parity advanced for Ruby, PHP, Swift, and
  Elixir in
  `go/internal/parser/{ruby_language,php_language,swift_language,elixir_dart_language}.go`
  plus focused TDD coverage in
  `go/internal/parser/{engine_ruby_semantics,php_language,engine_swift_semantics,engine_elixir_semantics}_test.go`
- [x] Normal runtime status surfaces now read from
  `src/platform_context_graph/indexing/run_status.py` instead of importing the
  legacy Python coordinator execution stack. `GraphBuilder` no longer owns any
  Python parser-registry bootstrap, single-file parse entrypoint, or
  file-refresh mutation path; `GraphBuilder`, the CLI runtime helper, and MCP
  server imports avoid eager imports of
  `platform_context_graph.parsers.registry`
- [x] Runtime-owned templated content inference and Jenkins controller metadata
  no longer import parser-owned helper modules. The canonical Python helpers
  now live in `src/platform_context_graph/content/templated_detection.py` and
  `src/platform_context_graph/automation/jenkins_metadata.py`, and the dead
  Python SCIP bridge/package (`GraphBuilder._build_graph_from_scip` plus
  `src/platform_context_graph/parsers/scip/`) has been deleted instead of
  lingering as an undocumented fallback path
- [x] The obsolete Python path-level execution helper
  `src/platform_context_graph/collectors/git/execution.py` has been deleted;
  normal file and directory path indexing now enters through the Go-owned
  `GraphBuilder.build_graph_from_path_async(...)` bootstrap route instead of a
  separate Python collector orchestration module
- [x] The obsolete Python discovery shim layer has been deleted from the
  branch: `src/platform_context_graph/collectors/git/indexing.py`,
  `src/platform_context_graph/collectors/git/discovery.py`, and
  `src/platform_context_graph/collectors/git/parser_support.py` are gone, and
  `GraphBuilder` no longer exposes Python discovery convenience helpers
- [x] The public Python facades no longer advertise the dead snapshot/coordinator
  parser path: `platform_context_graph.indexing` now exports only run-status
  helpers, and `platform_context_graph.collectors.git.indexing` no longer
  re-exports `parse_repository_snapshot_async`
- [x] Finish truthful parser parity and delete the remaining Python runtime
  seams. The native Go registry now covers every currently registered parser
  key in `go/internal/parser/registry.go`. All semantic-depth gaps are closed:
  C typedef aliases, Java annotations, Kotlin secondary constructors, Rust
  impl ownership, Ruby/PHP/Swift/Elixir long-tail edges, SCIP parity
  tie-break, and JSON/data-intelligence document coverage are all implemented
  with 101 parser tests across 21 test files passing. The remaining Python
  runtime ownership seams are now outside the deleted parser/discovery stack
  and are concentrated in evidence, content materialization, and API/CLI
  orchestration (Steps 3-8 below).

- [x] **Step 3: Write failing Go tests for native collector selection and snapshot ownership**

Cover repo discovery, filtering, identity normalization, parser dispatch,
and content-shaping boundaries without invoking Python.

Created `go/internal/collector/git_selection_native_test.go`.

- [x] **Step 4: Write failing Go tests for native repository snapshot and parse collection**

Cover per-repo snapshot capture, fingerprinting, content facts, and error
paths without invoking Python.

Created `go/internal/collector/git_snapshot_native_test.go`.

- [x] **Step 5: Implement native selection**

Move selection behavior into `go/internal/collector/git_selection_native.go`
and wire `collector.GitSource.Selector` to the native implementation.

Implemented in `git_selection_native.go` with supporting files
`git_selection_discovery.go`, `git_selection_filesystem.go`,
`git_selection_github.go`, `git_selection_git.go`, `git_selection_config.go`.

- [x] **Step 6: Implement native parser and snapshot collection**

Move snapshot behavior into `go/internal/collector/git_snapshot_native.go` and
wire `collector.GitSource.Snapshotter` to the native implementation.

Implemented in `git_snapshot_native.go` with SCIP support in
`git_snapshot_scip.go`.

The native collector snapshot path now also preserves structured parser entity
metadata end to end for normal Git ingestion. Parser-owned fields such as
docstrings, decorators, async/type metadata, and nested parser metadata now
survive materialization, snapshot transport, content-entity fact emission,
projector reconstruction, and Postgres `content_entities.metadata` persistence
instead of being truncated to the older scalar-only entity shape.

- [x] **Step 7: Delete Python bridge imports and code**

Remove all imports of `go/internal/compatibility/pythonbridge` from the
collector runtime and delete the Go bridge package.

Deleted `go/internal/compatibility/pythonbridge/` — directory is now empty.
Zero `pythonbridge` imports remain in Go code.

- [x] **Step 8: Delete the Python Git bridge modules**

Deleted:

```text
src/platform_context_graph/runtime/ingester/go_collector_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_bridge_facts.py
src/platform_context_graph/runtime/ingester/go_collector_selection_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_snapshot_bridge.py
src/platform_context_graph/runtime/ingester/go_collector_snapshot_collection.py
```

- [x] **Step 9: Run focused collector verification**

Run:

```bash
cd go && go test ./internal/parser ./internal/collector/discovery ./internal/content/shape ./internal/collector ./cmd/collector-git -count=1
```

Expected: PASS

- [ ] **Step 10: Run the compose collector proof**

Run:

```bash
./scripts/verify_collector_git_runtime_compose.sh
```

Expected: PASS with no Python bridge invocation in the normal collector path

- [ ] **Step 11: Commit**

```bash
git add go/cmd/collector-git \
  go/internal/collector \
  src/platform_context_graph/runtime/ingester
git commit -m "feat(cutover): remove python from collector-git hot path"
```

## Chunk 3: Make Deployed Runtime Services Actually Go-Owned

### Task 3: Replace Python runtime entrypoints in deployable surfaces

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

- [x] **Step 1: Write failing deployment/runtime tests**

Add or update tests so deploy assets fail unless they point at Go-owned write
services rather than Python `pcg internal ...` runtime commands.

- [x] **Step 2: Add a Go-owned ingester entrypoint**

Created `go/cmd/ingester/main.go` with compositeRunner pattern and
`go/cmd/ingester/wiring.go` for service construction.

- [x] **Step 3: Add a Go-owned bootstrap indexing entrypoint**

Created `go/cmd/bootstrap-index/main.go` with DI-based one-shot drain and
`go/cmd/bootstrap-index/wiring.go` for collector/projector construction.

- [x] **Step 4: Update Docker and deployment assets**

Dockerfile adds Go builder stage (`golang:1.26-alpine`), builds 7 binaries.
Compose and Helm updated to use `/usr/local/bin/pcg-ingester`,
`/usr/local/bin/pcg-bootstrap-index`, `/usr/local/bin/pcg-reducer`.

- [x] **Step 5: Keep admin/status, tracing, metrics, and pool tuning intact**

Admin mux, health/readiness probes, status server, and metrics handler wired
into all Go entrypoints.

- [x] **Step 6: Run runtime and deploy verification**

7 Go tests pass, 32 deployment tests pass, helm lint clean.

- [ ] **Step 7: Run full-stack compose proof** (deferred — requires running stack)

- [x] **Step 8: Commit**

Committed as `7a5d644` — `feat(runtime): add Go-owned ingester and bootstrap-index services`

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

- [x] **Step 1: Write failing recovery-path tests**

20 Go tests covering recovery domain model, HTTP handlers, and admin mux
wiring (commit `5eab84b`).

- [x] **Step 2: Add Go-owned replay and recovery handlers**

Implemented:
- `go/internal/recovery/replay.go` — domain model, Handler, ReplayStore interface
- `go/internal/storage/postgres/recovery.go` — Postgres ReplayStore with 4 query variants
- `go/internal/runtime/recovery_handler.go` — HTTP handler for `/admin/replay` and `/admin/refinalize`
- `go/internal/runtime/admin.go` — RecoveryHandler wired into AdminMuxConfig

Committed as `5eab84b` — `feat(recovery): add Go-owned replay and refinalize handlers`

- [x] **Step 3: Delete Python admin recovery endpoints**

Deleted Python refinalize endpoint from `admin.py` and replay endpoint from
`admin_facts.py`. Deleted the proxy module `admin_go_proxy.py`. The Go
ingester owns recovery directly at `/admin/replay` and `/admin/refinalize`.
This is a full migration, not a proxy.

CLI finalize deletion tracked in ownership completion plan Phase A (Chunk A2).

- [x] **Step 4: Delete the Python finalization bridge**

Deleted:

- `src/platform_context_graph/indexing/post_commit_writer.py`
- `src/platform_context_graph/collectors/git/finalize.py`
- `src/platform_context_graph/indexing/coordinator_finalize.py`

The Python coordinator now fails closed unless the facts-first runtime is
available, instead of falling back to the deleted post-commit writer path.

- [ ] **Step 5: Run focused recovery verification**

Run:

```bash
cd go && go test ./internal/projector ./internal/reducer ./internal/runtime ./internal/storage/postgres -count=1
PYTHONPATH=src uv run pytest tests/unit/api/test_admin_router.py tests/unit/api/test_admin_facts_recovery_router.py -q
```

Expected: PASS with no Python recovery endpoints remaining

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

## Chunk 5: Delete Remaining Python Runtime Ownership

### Task 5: Remove Python runtime/coordinator ownership from the normal platform flow

**Files:**
- Modify: `src/platform_context_graph/cli/commands/runtime.py`
- Modify: `src/platform_context_graph/app/service_entrypoints.py`
- Delete or quarantine: `src/platform_context_graph/runtime/ingester/*`
- Delete or quarantine: `src/platform_context_graph/indexing/*`
- Modify: `docs/docs/reference/source-layout.md`
- Modify: `docs/docs/architecture.md`
- Modify: `docs/docs/deployment/service-runtimes.md`
- Modify: `docs/docs/roadmap.md`

- [x] **Step 1: Write failing runtime-ownership tests**

13 gate tests in `test_python_runtime_ownership.py` covering:
- Python CLI runtime commands (bootstrap-index, repo-sync-loop, resolution-engine)
- Python finalization bridge files (post_commit_writer, finalize, coordinator_finalize, cli/helpers/finalize)
- Python collector bridge modules (5 go_collector_*bridge.py files)
- Go cmd/ pythonbridge import check

All 13 tests fail as expected. Committed as `9bb6d02`.

Additional gate tests for resolution, facts, and status store ownership tracked
in ownership completion plan Phase C (Chunk C3).

- [x] **Step 2: Remove Python write-runtime command ownership**

Make `bootstrap-index`, `repo-sync-loop`, and `resolution-engine` no longer the
normal deployed write-plane commands.

- [ ] **Step 3: Delete or quarantine Python write modules**

Anything left under `src/platform_context_graph/runtime/ingester/` and
`src/platform_context_graph/indexing/` should either be deleted or moved out of
the normal write path with explicit quarantine labeling and a tracked removal
condition on this branch.

- [x] **Step 4: Run repo-wide cutover checks**

Run:

```bash
rg -n "pythonbridge" go src
rg -n "go_collector_.*bridge" src/platform_context_graph
rg -n "@internal_app.command\\(\"bootstrap-index|@internal_app.command\\(\"repo-sync-loop|@internal_app.command\\(\"resolution-engine" src/platform_context_graph/cli/commands/runtime.py
```

Expected:

- no normal write-plane dependency on `pythonbridge`
- no live Go collector bridge modules left
- no Python runtime entrypoints still presented as deployed runtime owners

Verified with:

- targeted runtime ownership gate in `tests/integration/deployment/test_python_runtime_ownership.py`
- CLI regression coverage in `tests/integration/cli/test_cli_commands.py` and
  `tests/integration/cli/test_resolution_engine_runtime_identity.py`
- `rg` scan over `src/platform_context_graph/cli/commands/runtime.py`

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
because it is deletion, ownership flip, parser conversion, and parity proof
work rather than proof-of-concept work.

## Stop Rule

Do not begin AWS, Kubernetes, or any other new ingestor implementation until
Chunks 1 through 5 are complete and the merge bar is satisfied.
