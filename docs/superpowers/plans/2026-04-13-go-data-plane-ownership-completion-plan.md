# Go Data Plane Ownership Completion Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development
> (if subagents available) or superpowers:executing-plans to implement this plan.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** extend Go write-plane ownership beyond deployment surfaces to cover
resolution domain logic, operational surfaces, and recovery endpoint migration
so the branch merges with honest Go ownership of the full write path.

**Architecture:** the Go projector and reducer service loops already exist. This
plan fills them with domain-specific logic so they stop delegating to Python.
Recovery and admin operations are migrated by deleting the Python endpoints
and letting the Go ingester own them directly. Resolution domain ports proceed
in parallel with Codex's Chunk 2 parser/collector work.

**Tech Stack:** Go, PostgreSQL, Neo4j, Docker Compose, Helm, OpenTelemetry.

**Companion ADR:**
[Go Data Plane Ownership Completion](../../docs/adrs/2026-04-13-go-data-plane-ownership-completion.md)

---

## Current Truth

The Go write plane has:

- projector service loop (`go/internal/projector/service.go`) that claims,
  loads facts, projects, and acks/fails work items
- reducer service loop (`go/internal/reducer/service.go`) that claims, executes
  domain handlers, and acks/fails intents
- recovery handlers (`go/internal/recovery/replay.go`,
  `go/internal/runtime/recovery_handler.go`) for replay and refinalize
- admin mux (`go/internal/runtime/admin.go`) with health, readiness, status,
  metrics, and recovery routes
- two reducer domain handlers: workload identity and cloud asset resolution
- Postgres stores for facts, work queue, projector queue, reducer queue,
  status, and recovery

The Go write plane does NOT have:

- platform materialization (infrastructure/runtime platform edge creation)
- projection decision recording (confidence, evidence persistence)
- shared projection intent workers (partition-based cross-domain edge draining)
- failure classification (exception-to-durable-metadata mapping)
- full projector fact stages (entity, file, relationship, workload projection)
- status store request lifecycle (scan/reindex tracking, coverage metrics)
- Python admin recovery endpoints deleted (Go ingester owns replay/refinalize)

## Merge Bar Extension

In addition to the existing cutover merge bar, this plan adds:

- Go projector owns all fact-to-graph/content/intent projection stages
- Go reducer owns platform materialization and shared projection intent
  processing
- Python admin recovery endpoints deleted; Go ingester owns replay/refinalize
- Go status store covers scan/reindex request lifecycle
- gate tests cover resolution, facts, and status store Python ownership removal

---

## Phase A: Recovery Endpoint Migration

### Chunk A1: Delete Python Admin Recovery Endpoints

**Prerequisite work completed:**

- [x] Go recovery domain model in `go/internal/recovery/replay.go` (commit `5eab84b`)
- [x] Go HTTP recovery handler in `go/internal/runtime/recovery_handler.go` (commit `5eab84b`)
- [x] Go admin mux wires RecoveryHandler at `/admin/replay` and `/admin/refinalize` (commit `5eab84b`)
- [x] Postgres RecoveryStore with replay and refinalize queries (commit `5eab84b`)
- [x] 20 Go tests covering recovery domain, HTTP handlers, and admin mux (commit `5eab84b`)
- [x] RecoveryHandler wired into ingester via `StatusAdminOption` functional options
- [x] Ingester admin mux serves `/admin/replay` and `/admin/refinalize` directly

**Migration completed — Python endpoints deleted:**

- [x] **Step 1: Delete Python refinalize endpoint from admin.py**

Removed `RefinalizeRequest`, `_finalization_state`, `_finalization_lock`,
`_update_finalization_state`, `_utc_now_iso`, `_load_target_repositories`,
`_repair_repository_coverage`, `_run_refinalization`, `refinalize` endpoint,
and `refinalize_status` endpoint. Kept only `reindex` and
`shared_projection_tuning_report` endpoints.

- [x] **Step 2: Delete Python replay endpoint from admin_facts.py**

Removed `ReplayFailedFactsRequest` model and `replay_failed_facts` endpoint.
Kept dead-letter, skip, backfill, replay-events query, work-items query, and
projection decisions query endpoints.

- [x] **Step 3: Delete Python Go proxy module**

Deleted `src/platform_context_graph/api/routers/admin_go_proxy.py` and
`tests/unit/api/test_admin_go_proxy.py`. The proxy approach was wrong — this
is a full migration, not a bridge.

- [x] **Step 4: Update Python tests for remaining endpoints**

Rewrote `tests/unit/api/test_admin_router.py` to cover only `reindex` and
`shared_projection_tuning_report`. Rewrote
`tests/unit/api/test_admin_facts_recovery_router.py` to cover dead-letter,
skip, backfill, and replay-events query (no replay tests).

- [x] **Step 5: Remove PCG_INGESTER_ADMIN_URL from docker-compose**

Removed the proxy env var from the Python API service since there is no proxy.

- [x] **Step 6: Run admin verification**

```bash
PYTHONPATH=src uv run pytest tests/unit/api/test_admin_router.py \
  tests/unit/api/test_admin_facts_recovery_router.py -q
```

Result: 8 passed

### Chunk A2: Delete Python CLI Finalize Bridge

**Files:**
- Delete: `src/platform_context_graph/cli/helpers/finalize.py`
- Modify: `src/platform_context_graph/cli/commands/basic.py`

- [x] **Step 1: Delete the Python finalize CLI helper**

Deleted `cli/helpers/finalize.py`, removed `finalize_helper` import from
`cli/cli_helpers.py` and `cli/main.py`.

- [x] **Step 2: Stub the `pcg finalize` CLI command**

Replaced command body with a deprecation message directing operators to the Go
ingester admin endpoints (`/admin/refinalize`, `/admin/replay`). Command is
marked `deprecated=True` in Typer and exits with code 1.

- [x] **Step 3: Run CLI verification**

```bash
PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q
```

Result: 32 passed

### Chunk A3: Update Documentation For Go Recovery Surfaces

**Files:**
- Modify: `docs/docs/reference/http-api.md`
- Modify: `docs/docs/reference/cli-reference.md`
- Modify: `docs/docs/adrs/2026-04-12-cutover-and-legacy-bridge.md`

- [x] **Step 1: Document Go-owned recovery endpoints**

Updated HTTP API reference: removed Python refinalize/status endpoints,
documented Go ingester `/admin/refinalize` and `/admin/replay` as the
authoritative recovery surface.

- [x] **Step 2: Update CLI reference**

Marked `pcg finalize` as deprecated in the CLI command map, noting Go ingester
owns recovery.

- [x] **Step 3: Update cutover ADR bridge inventory**

Rewrote bridge inventory to split into "Go-owned (Python deleted)" and "Still
Python-owned (pending deletion)" sections. Recovery endpoints and CLI finalize
helper listed as deleted.

- [x] **Step 4: Run docs verification**

Run:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

Expected: PASS

- [x] **Step 5: Commit**

Committed in the recovery migration wave before the subsequent parser and
runtime cutover slices landed.

```bash
git add docs/docs/reference/http-api.md docs/docs/reference/cli-reference.md \
  docs/docs/adrs/2026-04-12-cutover-and-legacy-bridge.md
git commit -m "docs(recovery): document Go-owned replay and refinalize surfaces"
```

---

## Phase B: Resolution Domain Ownership

### Chunk B1: Go Platform Materialization

**Files:**
- Create: `go/internal/reducer/platform_materialization.go`
- Create: `go/internal/reducer/platform_materialization_test.go`
- Create: `go/internal/reducer/platform_families.go`
- Create: `go/internal/reducer/platform_families_test.go`
- Modify: `go/internal/reducer/registry.go`
- Modify: `go/internal/reducer/defaults.go`

- [x] **Step 1: Write failing tests for platform family inference**

Cover:
- Terraform runtime family definitions (ECS, EKS, Lambda, GKE, AKS, etc.)
- runtime platform kind inference from resource kinds
- GitOps platform kind and ID inference from config metadata
- infrastructure platform descriptor extraction from Terraform content
- canonical platform ID construction: `platform:kind:provider:discriminator:environment:region`

- [x] **Step 2: Implement platform families**

Port the 8 registered Terraform runtime families and all inference functions
from `resolution/platform_families.py` into Go.

Created `go/internal/reducer/platform_families.go` (8 families, 7 inference
functions) and `go/internal/reducer/platforms.go` (CanonicalPlatformID,
InferRuntimePlatformKind, InferInfrastructurePlatformDescriptor). 18 tests.

- [ ] **Step 3: Write failing tests for platform materialization**

Cover:
- runtime platform edge creation (RUNS_ON)
- infrastructure platform edge creation (PROVISIONS_PLATFORM)
- platform node creation with canonical identity
- idempotent materialization (re-running produces same graph state)

- [ ] **Step 4: Implement platform materialization reducer domain**

Port `materialize_runtime_platform()` and
`materialize_infrastructure_platforms()` from `resolution/platforms.py`.
Register as a reducer domain handler.

- [x] **Step 5: Run platform verification**

Run:

```bash
cd go && go test ./internal/reducer/... -count=1
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add go/internal/reducer/
git commit -m "feat(reducer): add Go-owned platform materialization domain"
```

### Chunk B2: Go Projection Decision Recording

**Files:**
- Create: `go/internal/projector/decisions.go`
- Create: `go/internal/projector/decisions_test.go`
- Create: `go/internal/storage/postgres/decisions.go`
- Create: `go/internal/storage/postgres/decisions_test.go`

- [x] **Step 1: Write failing tests for decision model**

Cover:
- projection decision construction with confidence (0.6-0.9)
- evidence row construction with fact linkage (limit 20)
- decision persistence and retrieval
- evidence linkage integrity

- [x] **Step 2: Implement decision domain model**

Create Go types for projection decisions and evidence rows matching the Python
`resolution/decisions/models.py` contract.

- [x] **Step 3: Implement Postgres decision store**

Port the decision persistence from `resolution/decisions/postgres.py`.

- [x] **Step 4: Wire into projector runtime**

Add decision recording as a post-projection step in the projector runtime.

- [x] **Step 5: Run decision verification**

Run:

```bash
cd go && go test ./internal/projector/... ./internal/storage/postgres/... -count=1
```

Expected: PASS (may require build tag isolation if collector package is broken)

- [x] **Step 6: Commit**

```bash
git add go/internal/projector/decisions.go go/internal/projector/decisions_test.go \
  go/internal/storage/postgres/decisions.go go/internal/storage/postgres/decisions_test.go
git commit -m "feat(projector): add Go-owned projection decision recording"
```

### Chunk B3: Go Shared Projection Intent Workers

**Files:**
- Create: `go/internal/reducer/shared_projection.go`
- Create: `go/internal/reducer/shared_projection_test.go`
- Create: `go/internal/reducer/partitioning.go`
- Create: `go/internal/reducer/partitioning_test.go`
- Create: `go/internal/storage/postgres/shared_intents.go`
- Create: `go/internal/storage/postgres/shared_intents_test.go`

- [x] **Step 1: Write failing tests for stable partitioning**

Cover:
- SHA256-based partition assignment stability
- partition-key-to-partition-id mapping
- row filtering by partition

- [x] **Step 2: Implement partitioning**

Port `resolution/shared_projection/partitioning.py` partition logic.

Created `go/internal/reducer/partitioning.go` with SHA256-based
PartitionForKey. 5 tests including cross-language parity check.

- [x] **Step 3: Write failing tests for shared intent store**

Cover:
- intent emission (platform infrastructure, platform runtime, dependency)
- partition-based intent claiming with lease
- stale/superseded intent cleanup
- intent completion lifecycle

- [x] **Step 4: Implement shared intent Postgres store**

Port `resolution/shared_projection/postgres.py`.

Created `go/internal/reducer/shared_projection.go` (domain model,
BuildSharedProjectionIntent with deterministic SHA256 IDs, RowsForPartition),
`go/internal/storage/postgres/shared_intents.go` (UpsertIntents, ListIntents,
ListPendingDomainIntents, MarkIntentsCompleted), and
`schema/data-plane/postgres/008_shared_projection_intents.sql`. 11 tests
across model and store layers.

- [ ] **Step 5: Write failing tests for shared projection workers**

Cover:
- platform partition processing (infrastructure-platform edges)
- dependency partition processing (repo/workload dependency edges)
- lease claiming and release
- stale intent cleanup during processing

- [ ] **Step 6: Implement shared projection domain handlers**

Port `resolution/shared_projection/runtime.py` platform and dependency
partition processors. Register as reducer domain handlers.

- [x] **Step 7: Run shared projection verification**

Run:

```bash
cd go && go test ./internal/reducer/... ./internal/storage/postgres/... -count=1
```

Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add go/internal/reducer/shared_projection.go go/internal/reducer/shared_projection_test.go \
  go/internal/reducer/partitioning.go go/internal/reducer/partitioning_test.go \
  go/internal/storage/postgres/shared_intents.go go/internal/storage/postgres/shared_intents_test.go
git commit -m "feat(reducer): add Go-owned shared projection intent workers"
```

### Chunk B4: Go Failure Classification

**Files:**
- Create: `go/internal/projector/failure_classification.go`
- Create: `go/internal/projector/failure_classification_test.go`

- [x] **Step 1: Write failing tests for failure classification**

Cover:
- Neo4j transient error mapping
- timeout and deadline exceeded classification
- input validation error classification
- resource exhaustion classification
- retry disposition assignment (retry, skip, dead-letter)
- stage error unwrapping

- [x] **Step 2: Implement failure classification**

Port `resolution/orchestration/failure_classification.py` into Go. Wire into
projector and reducer service error paths.

- [x] **Step 3: Run classification verification**

Run:

```bash
cd go && go test ./internal/projector/... -count=1
```

Expected: PASS

- [x] **Step 4: Commit**

```bash
git add go/internal/projector/failure_classification.go \
  go/internal/projector/failure_classification_test.go
git commit -m "feat(projector): add Go-owned failure classification"
```

### Chunk B5: Go Projector Fact-Stage Expansion

**Files:**
- Create: `go/internal/projector/stage_entities.go`
- Create: `go/internal/projector/stage_entities_test.go`
- Create: `go/internal/projector/stage_files.go`
- Create: `go/internal/projector/stage_files_test.go`
- Create: `go/internal/projector/stage_relationships.go`
- Create: `go/internal/projector/stage_relationships_test.go`
- Create: `go/internal/projector/stage_workloads.go`
- Create: `go/internal/projector/stage_workloads_test.go`
- Modify: `go/internal/projector/runtime.go`

- [x] **Step 1: Write failing tests for entity projection stage**

Cover:
- class, function, method entity projection from file payloads
- entity deduplication within scope generation
- batch streaming for memory-bounded entity processing
- entity-to-graph record materialization

- [x] **Step 2: Implement entity projection stage**

Port `resolution/projection/entities.py`.

- [x] **Step 3: Write failing tests for file projection stage**

Cover:
- file entity iteration and deduplication
- file-to-graph record materialization

- [x] **Step 4: Implement file projection stage**

Port `resolution/projection/files.py`.

- [x] **Step 5: Write failing tests for relationship projection stage**

Cover:
- cross-repo import and dependency relationship projection
- relationship-to-graph record materialization

- [x] **Step 6: Implement relationship projection stage**

Port `resolution/projection/relationships.py`.

- [x] **Step 7: Write failing tests for workload projection stage**

Cover:
- workload identity and runtime materialization
- workload-to-graph record materialization

- [x] **Step 8: Implement workload projection stage**

Port `resolution/projection/workloads.py`.

- [x] **Step 9: Wire stages into projector runtime**

Update `go/internal/projector/runtime.go` to dispatch through the full stage
sequence: repositories -> files -> entities -> relationships -> workloads ->
platforms.

- [x] **Step 10: Run projector verification**

Run:

```bash
cd go && go test ./internal/projector/... -count=1
```

Expected: PASS

- [x] **Step 11: Commit**

```bash
git add go/internal/projector/
git commit -m "feat(projector): add Go-owned fact projection stages"
```

---

## Phase C: Operational And Validation Surfaces

### Chunk C1: Build Tag Isolation For Storage Postgres Tests

**Files:**
- Modify: `go/internal/storage/postgres/recovery.go`
- Create: `go/internal/storage/postgres/recovery_test.go`
- Potentially modify other `*_test.go` files for build tag consistency

- [ ] **Step 1: Add build tag to isolate recovery tests**

Add `//go:build !collector_integration` or similar tags so recovery and
resolution store tests can run independently when the collector package has
compilation errors from in-progress work.

- [ ] **Step 2: Verify isolated test execution**

Run:

```bash
cd go && go test -tags '!collector_integration' ./internal/storage/postgres/... -count=1
```

Expected: PASS for recovery and resolution tests regardless of collector state

- [x] **Step 3: Commit**

Landed in the Phase C operational surface wave that also introduced the status
request store and parity verification.

```bash
git add go/internal/storage/postgres/
git commit -m "test(storage): add build tag isolation for recovery tests"
```

### Chunk C2: Go Status Store Parity

**Files:**
- Create: `go/internal/runtime/status_requests.go`
- Create: `go/internal/runtime/status_requests_test.go`
- Create: `go/internal/storage/postgres/status_requests.go`
- Create: `go/internal/storage/postgres/status_requests_test.go`
- Modify: `go/internal/runtime/status_server.go`

- [ ] **Step 1: Write failing tests for status request lifecycle**

Cover:
- scan request creation and claim
- reindex request creation and claim
- request completion and status reporting
- repository coverage metrics retrieval

- [ ] **Step 2: Implement status request domain model**

Port the request lifecycle from `runtime/status_store_runtime.py`.

- [ ] **Step 3: Implement Postgres status request store**

Port the status request persistence from `runtime/status_store_db.py`.

- [ ] **Step 4: Wire into status server**

Add request lifecycle routes to the admin mux via the status server.

- [ ] **Step 5: Run status verification**

Run:

```bash
cd go && go test ./internal/runtime/... ./internal/storage/postgres/... -count=1
```

Expected: PASS

- [x] **Step 6: Commit**

Landed in the Phase C operational surface wave that also introduced the status
request store and parity verification.

```bash
git add go/internal/runtime/status_requests.go go/internal/runtime/status_requests_test.go \
  go/internal/storage/postgres/status_requests.go go/internal/storage/postgres/status_requests_test.go \
  go/internal/runtime/status_server.go
git commit -m "feat(runtime): add Go-owned status request lifecycle"
```

### Chunk C3: Extended Gate Tests

**Prerequisite work completed:**

- [x] Initial gate tests for Python runtime commands, finalization bridge,
  collector bridge, and pythonbridge imports (commit `9bb6d02`)

**Files:**
- Modify: `tests/integration/deployment/test_python_runtime_ownership.py`

- [ ] **Step 1: Add resolution ownership gate tests**

Add test classes:
- `TestPythonResolutionOrchestrationRemoved`: verify
  `resolution/orchestration/engine.py` and `resolution/orchestration/runtime.py`
  are deleted
- `TestPythonResolutionProjectionRemoved`: verify
  `resolution/projection/{entities,files,relationships,workloads}.py` are deleted
- `TestPythonSharedProjectionRemoved`: verify
  `resolution/shared_projection/runtime.py` and `emission.py` are deleted
- `TestPythonPlatformMaterializationRemoved`: verify
  `resolution/platforms.py` and `platform_families.py` are deleted

- [ ] **Step 2: Add facts and status store gate tests**

Add test classes:
- `TestPythonFactsWorkQueueRemoved`: verify
  `facts/work_queue/postgres.py` and `facts/work_queue/claims.py` are deleted
- `TestPythonStatusStoreRemoved`: verify `runtime/status_store_runtime.py` and
  `runtime/status_store_db.py` are deleted

- [ ] **Step 3: Run gate tests (expect failures)**

Run:

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_python_runtime_ownership.py -q
```

Expected: all new tests FAIL (Python files still exist)

- [x] **Step 4: Commit**

Landed in the Phase C operational surface wave alongside the extended
ownership-gate assertions.

```bash
git add tests/integration/deployment/test_python_runtime_ownership.py
git commit -m "test(cutover): extend ownership gate tests for resolution and facts"
```

### Chunk C4: Compose Verification And Integration Tests

**Files:**
- Modify: `scripts/verify_collector_git_runtime_compose.sh` (if needed)
- Create: `tests/integration/deployment/test_go_write_plane_parity.py`

- [ ] **Step 1: Write Go write-plane parity integration tests**

Cover:
- Go ingester -> projector -> reducer -> graph write flow
- recovery replay produces expected work item state changes
- refinalize re-enqueues active scope generations
- platform materialization produces expected graph edges

- [ ] **Step 2: Update compose scripts if needed**

Ensure compose verification scripts exercise the Go write-plane services and
report failures clearly.

- [ ] **Step 3: Run integration verification**

Run:

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/ -q
```

Expected: PASS for new parity tests, existing gate tests still FAIL (expected)

- [x] **Step 4: Commit**

Landed in the Phase C operational surface wave that added compose-backed Go
write-plane parity verification.

```bash
git add scripts/ tests/integration/deployment/
git commit -m "test(parity): add Go write-plane integration tests"
```

---

## Remaining Effort

| Phase | Chunks | Effort | Blocked on |
| --- | --- | --- | --- |
| A | ~~A1~~, ~~A2~~, ~~A3~~ | **Done** | — |
| B | B1, B2, B3, B4, B5 | Large | Nothing |
| C | C1, C2, C3, C4 | Medium | Phase B for gate test coverage |

Phases A and B can run in parallel. Phase C depends on Phase B.

The indexing coordinator (`src/platform_context_graph/indexing/`, 23 files)
remains out of scope for this plan because it is tightly coupled to the
collector pipeline and blocked on Chunk 2. It will be covered by a separate
plan after the native collector cutover completes.

## Validation Gate

This plan should not be called complete without:

```bash
cd go && go test ./internal/projector/... ./internal/reducer/... \
  ./internal/runtime/... ./internal/storage/postgres/... \
  ./internal/recovery/... -count=1
PYTHONPATH=src uv run pytest tests/integration/deployment/ -q
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

## Stop Rule

Do not start new collector families or new reducer domains not listed in this
plan until Phases A through C are complete and the cutover merge bar is
satisfied.
