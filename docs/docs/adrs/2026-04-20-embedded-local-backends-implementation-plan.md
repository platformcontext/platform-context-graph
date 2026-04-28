# Implementation Plan: Embedded Local Backends For PCG Desktop Mode

**Date:** 2026-04-20
**Owner:** Allen Sanabria
**Tracks ADR:** `2026-04-20-embedded-local-backends-desktop-mode.md`
**Status:** Draft — ready for review

---

## Executive Summary

Deliver a `local` storage profile that runs PCG end-to-end against
embedded backends — **Ladybug** (graph, cgo) and
**`fergusstrange/embedded-postgres`** (relational, subprocess) — without
changing the service-profile deployment contract. Estimated effort: **~8
weeks, one senior dev**, split across 11 phases with independent exit
criteria and telemetry obligations. Includes a dogfood-ready
`pcg watch .` runtime so PCG devs can use PCG while building PCG.

### Success criteria (goal-backward)

A developer on macOS or Linux can run, with no external services:

```bash
brew install pcg                 # or: go install ./cmd/pcg
pcg index .                      # local profile: embeds Postgres + Ladybug
pcg list                         # reads the same stores in-process
pcg analyze callers process_pay  # graph-backed analysis
pcg mcp setup                    # IDE/agent MCP against same in-process data
```

And on the service side, **zero behavioral regressions**:

- `docker compose up --build` still brings up Neo4j + external Postgres + all runtimes
- All existing CLAUDE.md Go test gates pass unchanged
- Neo4j adapter, Postgres adapter, Cypher statements, and pool tuning for
  the service profile are byte-identical to today

### Non-goals

- Desktop GUI. Only the CLI + MCP surfaces.
- New query language. Cypher is preserved end-to-end.
- Multi-writer Ladybug. Single-writer serialization is explicitly accepted
  for the local profile.
- Replacing Neo4j in service deployments.

### Production-untouched guarantee

The local profile is **purely additive**. Concrete invariants:

- No change to default `docker compose up --build` behavior. Without
  `PCG_STORAGE_PROFILE=local` set, the binary resolves the service
  profile and opens Neo4j + external Postgres exactly like today.
- No change to Helm values, deployment shapes, or runtime images.
  `deploy/helm/**` and `Dockerfile` are not modified for local support.
- No change to existing Cypher, Postgres schema, or fact/queue contracts
  under the service profile. Ladybug-specific rewrites (FTS, `db.labels`)
  live behind the adapter and are never compiled into the service read
  path (see D3).
- Ladybug cgo is gated behind a build tag (`pcg_local`). Service images
  are built without the tag and carry no libkuzu.so, no embedded-postgres
  binary, no local-only code paths.
- CI gates: a dedicated job builds without `pcg_local`, runs the full
  service-profile test matrix, and diff-checks that no shared file
  changed service-observable behavior (see Phase 9, G9.4).

### Dogfooding use case (load-bearing)

PCG must be usable **locally, live, against its own repo, while developing
PCG**. This is a first-class use case, not a stretch goal:

1. **Brew-installable single binary.** `brew install pcg` or
   `go install ./cmd/pcg` yields one binary that ships Ladybug (cgo) +
   embedded-postgres. No Docker, no Neo4j, no shell scripts required.
2. **Live watch mode.** `pcg watch .` runs in the background, detects
   file changes under the repo, and incrementally re-indexes the changed
   entities into the local stores.
3. **Same-repo introspection.** While working on PCG code in this repo,
   the developer can query the local graph via CLI/MCP to answer
   "who calls this?", "what does this function touch?", "what breaks if
   I change this signature?" — with zero network round-trips, reading
   embedded stores in-process.
4. **Token savings.** MCP tools backed by the local profile replace
   blind grep/read cycles during AI-assisted development. Every answered
   relationship query avoids dozens of Read/Grep tool calls.

Success test for dogfooding: from a clean checkout of
`platform-context-graph`, a developer:

1. runs `pcg watch .` (starts the local daemon: Ladybug + embedded PG
   + incremental indexer + MCP server on
   `~/.pcg/local/<hash>/mcp.sock`),
2. configures Claude Code / Cursor with a stdio proxy entry
   `command: pcg mcp stdio` (the proxy auto-discovers and connects to
   the running daemon socket — see D3 + Phase 7.5),
3. asks "who calls `OpenPostgres` across this repo?" and gets a
   correct answer in < 500 ms,
4. never starts Docker, Neo4j, or an external Postgres.

---

## Storage Flow: Local vs Service

The diagram below shows the same PCG surfaces (CLI, API, MCP, Ingester,
Reducer) routing through one storage contract, with profile selection
determining which adapter binds at process start and where write
serialization takes effect.

```mermaid
flowchart TB
  subgraph Surfaces["PCG surfaces (profile-agnostic)"]
    direction LR
    CLI["pcg CLI<br/>(index/list/analyze)"]
    API["pcg api start"]
    MCP["pcg mcp start"]
    ING["pcg-ingester"]
    RED["pcg-reducer"]
    BOOT["pcg-bootstrap-index"]
  end

  GIF["storage/graph.Driver<br/>+ storage/content.Pool<br/>(portable contracts — D1)"]

  Surfaces --> GIF

  GIF -->|PCG_STORAGE_PROFILE=local| LOCAL
  GIF -->|PCG_STORAGE_PROFILE=service| SERVICE

  subgraph LOCAL["LOCAL profile (single binary, no external services)"]
    direction TB
    LSW["GraphWriter mutex<br/>SINGLE-WRITER<br/>(serialized tx, parallel reads)"]
    LADY["Ladybug adapter<br/>(cgo — embedded graph)"]
    LDATA[("~/.pcg/local/graph/<br/>(Ladybug files)")]
    LPOOL["pgxpool<br/>MULTI-WRITER<br/>(N conns, N writers)"]
    EPG["embedded-postgres<br/>(real PG binary subprocess)"]
    LPGDATA[("~/.pcg/local/pg/<br/>(PGDATA)")]

    LSW --> LADY --> LDATA
    LPOOL --> EPG --> LPGDATA
  end

  subgraph SERVICE["SERVICE profile (unchanged — Docker Compose / Helm)"]
    direction TB
    NDRV["Neo4j driver<br/>MULTI-WRITER<br/>(server-side tx, bolt pool)"]
    NEO["Neo4j<br/>(external, clustered)"]
    SPOOL["pgxpool<br/>MULTI-WRITER<br/>(N conns, N writers)"]
    PG["Postgres<br/>(external, HA-capable)"]

    NDRV --> NEO
    SPOOL --> PG
  end

  LOCAL -.->|pcg export --graduate<br/>(Phase 8: dump Ladybug → Cypher<br/>replay into Neo4j + pg_dump/restore)| SERVICE

  classDef single fill:#fde68a,stroke:#b45309,color:#111
  classDef multi  fill:#bbf7d0,stroke:#166534,color:#111
  classDef store  fill:#e5e7eb,stroke:#374151,color:#111
  classDef iface  fill:#dbeafe,stroke:#1d4ed8,color:#111
  class LSW,LADY single
  class LPOOL,NDRV,SPOOL multi
  class LDATA,LPGDATA,EPG,NEO,PG store
  class GIF iface
```

**Reading the diagram.**

- **One contract, two adapters.** Every surface (`pcg`, `api`, `mcp`,
  `ingester`, `reducer`, `bootstrap-index`) writes through
  `storage/graph.Driver` + `storage/content.Pool`. D1 (interface
  extraction) is what lets this exist; until Phase 1 lands, adapters
  cannot be swapped.
- **Yellow boxes = single-writer.** In the local profile, the Ladybug
  adapter serializes **graph write transactions** behind a process-wide
  mutex. Reads stay parallel. This is the only place in PCG where we
  accept single-writer, and it only applies when
  `PCG_STORAGE_PROFILE=local`.
- **Green boxes = multi-writer.** Relational writes in the local profile
  still go through `pgxpool` into real Postgres — no serialization
  reshape on the relational side. The entire service profile
  (Neo4j + external Postgres) is multi-writer end-to-end and is
  byte-identical to today.
- **Graduation arrow.** `pcg export --graduate` (Phase 8) is the
  one-way bridge: dump Ladybug to Cypher + `pg_dump` the embedded
  cluster, then replay into an external Neo4j and restore into an
  external Postgres. No runtime crossover between profiles.

**Where serialization takes effect — exact call sites.**

| Profile | Graph writes | Graph reads | Relational writes | Relational reads |
| --- | --- | --- | --- | --- |
| `local` | **Serialized** via `LadybugDriver.WriteSession` mutex | Parallel (read-only cursors) | Multi-writer `pgxpool` → embedded PG | Multi-writer `pgxpool` |
| `service` | Multi-writer Neo4j bolt driver (server-side tx) | Multi-writer | Multi-writer `pgxpool` → external PG | Multi-writer `pgxpool` |

**What this implies for the plan.**

- Reducer batching (Phase 4, D4) only changes shape when the local
  adapter is bound. Under the service profile the reducer executes the
  same per-item tx pattern it does today.
- Telemetry (Phase 7, D7) labels every span/metric with
  `graph_backend={neo4j|ladybug}` so dashboards can segment
  single-writer latency without touching service-profile panels.
- The graduation path (Phase 8) is explicitly a **snapshot + replay**,
  not a live replication pipe. No shared write path between profiles.

---

## Current-State Grounding (pre-edit gate)

Before any code changes, the plan must answer the CLAUDE.md pre-edit gate
for each phase. These facts are established now and referenced below.

### Storage interface reality

- `go/internal/storage/neo4j/writer.go` defines `Executor` + `Statement`
  **only for source-local writes**. Canonical writers (`canonical_node_writer.go`,
  `edge_writer.go`, `semantic_entity.go`, `canonical_relationships.go`)
  and the query layer (`go/internal/query/neo4j.go`) use
  `neo4jdriver.DriverWithContext` directly.
- There is **no shared graph-writer interface** today spanning
  projector/reducer/query. Interface extraction is a critical-path item,
  not an afterthought.

### Runtime composition reality

- `go/internal/runtime/data_stores.go` exposes `OpenPostgres`,
  `OpenNeo4jDriver`, `LoadPostgresConfig`, `LoadNeo4jConfig`. Config is
  flat env-driven — no profile branching.
- `go/internal/app/app.go` wires `runtime.LoadConfig(serviceName)` and
  `runtime.NewLifecycle(cfg)`. Single seam candidate: add a storage
  profile branch right before driver open.

### CLI reality

- `go/cmd/pcg/basic.go` `runIndex` `syscall.Exec`s `pcg-bootstrap-index`.
  In local profile this must either (a) in-process import the bootstrap
  runtime or (b) pass profile env through to the exec'd binary.
- `pcg api start`, `pcg mcp start`, admin, analyze, find, service, ecosystem
  commands all construct API clients via `apiClient()` pointing at
  `http://localhost:8080`. Local mode either (a) keeps that by starting
  the API in-process or (b) adds an in-process client path.

### Cypher surface reality

- 552 Cypher statements across 62 files.
- 0 `apoc.*` uses (verified).
- 3 `shortestPath` call sites (`impact.go`, `code_call_chain.go` + 1 contract test).
- 1 `CALL { … }` subquery site (`impact.go:69`).
- 2 `db.index.fulltext.createNodeIndex` call sites (`graph/schema.go`).
- 1 `db.labels()` call site (test fixture).

### Observability reality (CLAUDE.md contract)

- All new code paths must register OTEL metrics/spans/structured logs.
- Metric prefix `pcg_dp_`. Dimension keys frozen in
  `go/internal/telemetry/contract.go`.
- New instruments go in `go/internal/telemetry/instruments.go`.
- `InstrumentedDB` pattern for new storage.

---

## Architectural Decisions (plan-level)

These decisions are made here, not deferred to code review:

### D1. Introduce `go/internal/storage/graph` interface package

A new package owns the **portable graph storage contract**. Both Neo4j and
Ladybug adapters implement it. Nothing in `go/internal/query`,
`go/internal/reducer`, `go/internal/projector`, or `go/internal/graph`
imports a driver type directly.

Contract shape (to be finalized in Phase 1):

```go
package graph

type Driver interface {
    ReadSession(ctx) (ReadSession, error)
    WriteSession(ctx) (WriteSession, error)
    Close(ctx) error
    Capabilities() Capabilities      // e.g., SingleWriter, FTS, VectorIndex
}

type ReadSession interface {
    Run(ctx, cypher string, params map[string]any) (Result, error)
    Close(ctx) error
}

type WriteSession interface {
    Execute(ctx, Statement) error
    ExecuteGroup(ctx, []Statement) error
    Close(ctx) error
}
```

Existing `neo4j.Executor`/`Statement` is promoted (renamed) into this
package. The source-local adapter keeps its narrow `Operation` enum but
implements the broader contract.

### D2. Storage profile seam at `go/internal/runtime/data_stores.go`

A single factory function picks the profile:

```go
func OpenGraphDriver(ctx, getenv) (graph.Driver, GraphConfig, error)
func OpenRelationalDB(ctx, getenv) (*sql.DB, PostgresConfig, error)
```

Both dispatch on `PCG_STORAGE_PROFILE` (`service` default, `local` opt-in).
No per-call-site `if profile == "local"` branches anywhere downstream.

### D3. Single-writer is **cross-process**, not just in-process

Codex-review correction (finding #1): a `sync.Mutex` inside the Ladybug
adapter fences goroutines inside ONE process. The local profile has
multiple entrypoints (`pcg index`, `pcg api start`, `pcg mcp start`,
`pcg watch`) that can all open the same data dir. A process-local
mutex is insufficient; without cross-process fencing, two concurrent
`pcg` invocations can corrupt the store.

The single-writer contract spans **three enforced layers**, from
outermost to innermost:

1. **Daemon-first topology.** `pcg watch` is the canonical local
   daemon. When it is running, other `pcg` commands MUST route writes
   through it — not open the store independently. CLI/API/MCP
   detection:
   - Check `~/.pcg/local/<data-dir-hash>/daemon.sock` exists and is
     reachable.
   - If yes: send writes over the unix socket (new `pcg localctl`
     client, same surface as remote HTTP API).
   - If no: proceed to layer 2.
2. **OS file lock on the data dir.** A standalone `pcg` command
   acquires `flock(~/.pcg/local/<hash>/write.lock, LOCK_EX | LOCK_NB)`
   before opening Ladybug for writes. Second concurrent command sees
   `EWOULDBLOCK` and either (a) retries on a bounded backoff or
   (b) exits with an actionable error naming the PID holding the
   lock. Ladybug/Kuzu's own data-dir lock is the ultimate backstop but
   we do not rely on its error message being human-actionable.
3. **In-process mutex.** Inside the holding process, the Ladybug
   adapter still wraps writes in a `sync.Mutex` (or buffered command
   channel) to serialize goroutines. Readers proceed concurrently.

Neo4j adapter keeps multi-writer semantics unchanged.

Acceptance tests for D3:
- `T-D3-1`: `pcg watch` running, second `pcg index` invocation routes
  through the daemon socket, produces identical graph as direct write.
- `T-D3-2`: no daemon, two simultaneous `pcg index` invocations:
  second exits with `error: local write lock held by PID=<n>
  (acquired <duration> ago)` within 500 ms; no store corruption.
- `T-D3-3`: daemon unreachable socket (stale sock file), CLI falls
  back to file-lock path and logs `daemon.socket_stale`.
- `T-D3-4`: fuzz-style contract test uses `testcontainers` to spin
  two Go binaries against the same Ladybug data dir for 60 s; asserts
  post-run integrity via Cypher read-back.

Concurrency invariants restated as a table:

| Writer source | Local profile enforcement | Service profile |
| --- | --- | --- |
| goroutines in one process | `sync.Mutex` in adapter | none needed |
| two pcg CLI invocations | OS `flock` on data dir | N/A |
| CLI + daemon | daemon socket routes external writers | N/A |
| two service-profile API replicas | N/A | Neo4j server-side tx |

### D4. Embedded Postgres uses the **real Postgres protocol**

`fergusstrange/embedded-postgres` spawns a Postgres binary. The rest of
`go/internal/storage/postgres/*.go` stays byte-identical because the
DSN PCG hands to pgx is interchangeable.

### D5. Cypher rewrites are gated behind a dialect helper

Rather than branching `if profile == "local"` at 6 sites, introduce a
`graph.Dialect` with functions like `FTSCreateIndex(name, labels,
props) string` and `ShortestPath(…) string`. Neo4j implementation
emits `CALL db.index.fulltext.createNodeIndex(…)`; Ladybug emits
`CALL CREATE_FTS_INDEX(…)`. Call sites stop caring which backend is
loaded.

### D6. Bootstrap-index becomes importable in-process for local profile

Add a thin `bootstrapindex.Run(ctx, cfg) error` entry that today's
`cmd/bootstrap-index/main.go` wraps. `pcg index` local-profile path
calls `bootstrapindex.Run` in-process rather than `syscall.Exec`.
Service profile keeps the exec behavior so Compose/K8s semantics are
identical.

### D7. In-process API + MCP for local profile

`pcg index`, `pcg list`, `pcg mcp start` in local profile spin up
the API + MCP handlers in-process against the same Ladybug + embedded
Postgres stores. Service profile still shells to external HTTP.
Selected via the same `PCG_STORAGE_PROFILE` seam.

### D8. Graduation is append-only export

`pcg export --graduate` streams local data out (Cypher statements for
graph, `pg_dump` for relational) for import into a service-profile
deployment. It does not do live replication. Users run it manually
when they outgrow local.

### D9. Watch mode is a dedicated long-running runtime

`pcg watch <path>` is a first-class runtime, not a flag on `pcg index`.
Rationale: watch mode owns a filesystem notifier, a debounced change
queue, an in-process re-indexer, and a supervision loop around the
embedded stores. None of those belong on a one-shot command.

Key contracts:

- **fsnotify-backed** on Linux/macOS (native APIs: inotify, FSEvents).
  No polling fallback by default.
- **Debounced batches**: coalesces bursts (editor save-all, `git
  checkout`, `git rebase`) into a single re-index window (default
  250 ms; configurable).
- **Respects `.pcgignore` + built-in excludes** (`.git/`,
  `node_modules/`, `bin/`, `dist/`, `.terraform/`). Watch never indexes
  inside those trees regardless of depth.
- **Editor-swap-file filter**: ignores `.swp`, `.swo`, `*~`, `*.tmp`,
  `.#*`, `#*#` so vim/emacs don't cause spurious re-indexes.
- **PID lockfile** at `~/.pcg/local/watch.pid` — only one watch
  process per data dir. Second invocation exits with actionable error.
- **Graceful shutdown** on SIGINT/SIGTERM: flushes pending change
  queue, closes embedded-postgres cleanly (no `SIGKILL`), releases PID
  lock. Zombie-PG recovery on next start (see R8).
- **Self-edit awareness**: when `pcg watch` is pointed at the
  platform-context-graph repo itself (dogfood path), re-index must not
  block on files the watch process's own embedded-postgres subprocess
  is writing (PGDATA is always excluded).

Watch mode is always single-writer on the graph side — it shares the
Ladybug mutex with any concurrent `pcg` CLI invocation via the same
data dir (see R9).

### D10. Single-binary packaging with build tag `pcg_local`

The brew formula and `go install` path produce one binary that embeds
Ladybug (cgo) and bundles the embedded-postgres download logic.
Concrete:

- Build tag `pcg_local` enables Ladybug driver registration and
  embedded-postgres subprocess management. Without the tag, those
  code paths are absent (service-only build, CI-gated).
- embedded-postgres binary is **downloaded on first run** (not
  embedded in the Go binary) to keep CLI size reasonable. Cached
  under `~/.pcg/local/pg-binaries/<version>/`. Download is
  checksummed and signature-verified.
- No dynamic libkuzu.so dependency on the host: the Ladybug cgo
  build statically links where feasible, falls back to a vendored
  shared lib under `~/.pcg/local/lib/` otherwise.
- `pcg version --profile` prints both `graph_backend` and
  `relational_backend` so users can verify the binary they installed.

---

## Phase Plan

Each phase is independently shippable (feature-flagged where needed) and
has its own exit criteria, telemetry, and tests. Phases are labeled
**S** (sequential — must complete before the next) or **P** (parallel —
can run alongside others).

### Phase 0 — Spike & grammar verification (S, ~3 days)

**Goal:** Prove Ladybug can execute a representative PCG Cypher subset
before committing to the full build-out.

**Pre-edit gate answers:**
1. Entry: None (new spike repo or `cmd/ladybug-spike`).
2. Phase order: Runs before Phase 1 scope is locked.
3. Data deps: None.
4. Re-trigger: None.

**Tasks:**
1. Build Ladybug from source on macOS + Linux via its documented
   `make release` path. Capture `libladybug.*` artifact size.
2. Clone archived `kuzudb/go-kuzu`; repoint cgo headers at Ladybug;
   smoke test `Open → Query → Close` on a 3-node/2-edge toy.
3. Port 20 representative Cypher statements from PCG (pick from
   `storage/neo4j/canonical_relationships.go`, `query/impact.go`,
   `query/code_call_chain.go`, `graph/schema.go`). Run each against
   Ladybug. Capture pass/fail and required rewrites.
4. Benchmark `CREATE` of 1M nodes + 3M edges + `shortestPath` on
   LDBC-SF1 fragment. Confirm seconds-class.

**Exit criteria:**
- Go binding runs at least one parameterized MATCH + MERGE.
- ≥ 90% of the 20-statement sample passes unchanged; remaining
  statements have documented rewrite candidates.
- 1M-node / 3M-edge load completes within 60 seconds single-threaded.

**Abort trigger:** If < 80% of the sample passes or the C API is
incompatible with `go-kuzu`, escalate back to ADR to reopen backend
selection before further work.

---

### Phase 1 — `go/internal/storage/graph` interface extraction (S, ~1 wk)

**Goal:** Land the portable graph contract without behavior change.
Neo4j adapter re-expressed behind it. Zero test regressions.

**Pre-edit gate:**
1. Entry: Every binary that opens a Neo4j driver —
   `cmd/api/main.go`, `cmd/mcp-server/main.go`, `cmd/bootstrap-index/main.go`,
   `cmd/ingester/main.go`, `cmd/reducer/main.go`. Read all.
2. Phase order: Blocks Phases 2, 3, 4.
3. Data deps: Existing runtime config.
4. Re-trigger: N/A.

**Scope:**
- New `go/internal/storage/graph/` package defining `Driver`,
  `ReadSession`, `WriteSession`, `Statement`, `Capabilities`,
  `Dialect`.
- Rename `storage/neo4j.Statement` → import alias; keep backwards
  type alias in `storage/neo4j` during migration.
- Neo4j adapter refactored to expose a `graph.Driver` constructor:
  `neo4j.NewDriver(neo4jdriver.DriverWithContext, database) graph.Driver`.
- `query.Neo4jReader` → `query.GraphReader` taking `graph.Driver`.
- Every call site in `query/`, `reducer/`, `projector/`, `graph/`
  migrated. No direct `neo4jdriver.DriverWithContext` imports outside
  `storage/neo4j/`, `cmd/*/main.go`, and `runtime/data_stores.go`.
- Dialect helper seeded with Neo4j implementation for FTS + shortest
  path. Local implementation stubbed returning `ErrNotImplemented`.

**Telemetry obligations:**
- Move existing `InstrumentedExecutor` metrics to wrap the interface
  rather than the concrete Neo4j type.
- Introduce `graph_backend` attribute on all storage metrics
  (`neo4j` | `ladybug`). Add to `telemetry/contract.go`.

**Tests:**
- Existing neo4j package tests must pass unchanged.
- New `storage/graph/contract_test.go` defines adapter conformance
  tests reusable by Ladybug later.

**Exit criteria:**
- `go test ./...` green.
- `grep -r "neo4j-go-driver" go/internal/query go/internal/reducer go/internal/projector go/internal/graph` returns zero matches.
- No production runtime performance regression (sampled on a fresh E2E
  run).

---

### Phase 2 — Embedded Postgres adapter (P with Phase 3, ~1 wk)

**Goal:** Boot `fergusstrange/embedded-postgres` from `pcg`, hand a DSN
to the existing `storage/postgres` code, run the same bootstrap DDL
against it.

**Pre-edit gate:**
1. Entry: `cmd/pcg/basic.go` `runIndex`, `cmd/pcg/service.go` API start,
   `runtime/data_stores.go`, `storage/postgres/schema.go`. Read all.
2. Phase order: Independent of Phases 1 and 3; merges before Phase 5.
3. Data deps: None.
4. Re-trigger: Schema migrations run exactly once per DB init.

**Scope:**
- New `go/internal/app/localpg/` package:
  - `Boot(ctx, dataDir, version) (*sql.DB, Stopper, error)`
  - Pin Postgres version (decision: 16.x, documented in ADR open questions).
  - Data dir: `$PCG_LOCAL_DIR/postgres` (default `~/.pcg/postgres`).
  - Writes `superuser`/`port`/`database` into a profile-scoped env
    that `LoadPostgresConfig` reads.
- `runtime.OpenRelationalDB` factory dispatching on `PCG_STORAGE_PROFILE`.
  When `local` and `PCG_POSTGRES_DSN` unset, boot embedded; else honor
  the provided DSN.
- Run `storage/postgres.ApplyBootstrap` against embedded DB on first boot.
- Stopper wired into `app.Lifecycle.Stop`.

**Telemetry obligations:**
- `pcg_dp_local_postgres_boot_seconds` histogram.
- `pcg_dp_local_postgres_running` gauge.
- Structured log event `local_postgres.booted` with `data_dir`,
  `version`, `port`.

**Tests:**
- `localpg_integration_test.go`: boot, run `SELECT 1`, apply schema,
  shut down, reboot against same data dir, verify idempotent.
- Matrix: `go test -tags=localpg ./internal/app/localpg/…` lane in CI.

**Exit criteria:**
- A Go test harness can replace any `NEO4J`-less Postgres test with
  embedded Postgres and pass existing `storage/postgres` tests
  byte-identically.
- Cold boot under 3 seconds on a warm data dir; under 10 seconds on
  first-time init.

**Risks:**
- Windows compatibility of `fergusstrange/embedded-postgres`.
  Mitigation: documented as deferred in ADR open questions; macOS +
  Linux land first.
- Version drift between embedded and service Postgres. Mitigation:
  explicit test asserting DDL parity on both.

---

### Phase 3 — Ladybug cgo adapter scaffolding (P with Phase 2, ~1 wk)

**Goal:** Land the cgo wrapper + `graph.Driver` implementation stub that
passes the Phase 1 contract tests for read/write.

**Pre-edit gate:**
1. Entry: `storage/graph/contract_test.go`. Read the full contract
   surface before implementation.
2. Phase order: Blocks Phases 4, 6.
3. Data deps: None.
4. Re-trigger: N/A.

**Scope:**
- Vendor or fork `kuzudb/go-kuzu` into `third_party/go-ladybug/` (MIT +
  MIT compatible).
- Repoint headers at Ladybug include path; update CGO flags.
- `go/internal/storage/ladybug/` package:
  - `Driver` struct holding cgo handle + serialization mutex.
  - `NewDriver(dbPath, readOnly bool) (*Driver, error)`.
  - `ReadSession` / `WriteSession` implementations.
  - `Capabilities()` returns `{SingleWriter: true, FTS: true, VectorIndex: true}`.
- Statement translation layer: accept `graph.Statement`, map to
  Ladybug-native parameter binding.
- Add Makefile target `make ladybug-build` that produces the static
  lib and the Go binary linking it.

**Telemetry obligations:**
- `pcg_dp_ladybug_query_duration_seconds` histogram (mirrors Neo4j).
- `pcg_dp_ladybug_write_serialization_wait_seconds` histogram for the
  single-writer mutex wait.
- `graph_backend=ladybug` attribute on all shared storage metrics.

**Tests:**
- `storage/ladybug/*_test.go` mirroring neo4j test suite.
- `storage/graph/contract_test.go` runs against Ladybug and passes.
- Known-gap tests marked with `t.Skip("ladybug-gap-<number>")` with
  a linked issue, not silently deleted.

**Exit criteria:**
- `CREATE NODE TABLE`, `CREATE REL TABLE`, `MERGE`, `MATCH`, `UNWIND`,
  `WITH`, `RETURN`, `ORDER BY`, `LIMIT`, parameters all green.
- cgo build works on macOS ARM + Linux x86.

**Risks:**
- go-kuzu cgo surface not 100% compatible with Ladybug headers.
  Mitigation: Phase 0 spike catches this before committing.
- Memory ownership edge cases on Ladybug result buffers. Mitigation:
  explicit test for large result sets + `runtime.SetFinalizer` audit.

---

### Phase 4 — Cypher dialect rewrites (S after Phase 1 + 3, ~3 days)

**Goal:** Introduce `graph.Dialect` backed by Neo4j and Ladybug
implementations. Migrate the 6 genuinely Neo4j-specific sites.

**Pre-edit gate:**
1. Entry: Each call site file + its callers. Read full function bodies.
2. Phase order: Requires `storage/graph` interface (Phase 1) and the
   Ladybug adapter (Phase 3).
3. Data deps: None.
4. Re-trigger: N/A.

**Scope:**
- `graph.Dialect` interface with methods:
  - `CreateFullTextNodeIndex(name, labels []string, props []string) string`
  - `ShortestPath(src, rel, dst, minHops, maxHops int) string`
  - `ListLabels() string`
- Neo4j dialect: emits today's exact Cypher.
- Ladybug dialect: emits FTS extension calls + GDS shortest-path syntax.
- Call-site migrations:
  - `go/internal/graph/schema.go` — 2 FTS index creations.
  - `go/internal/query/impact.go` — `CALL { … }` subquery (verify
    Ladybug binding) + `shortestPath` rewrite.
  - `go/internal/query/code_call_chain.go` — `shortestPath` rewrite.
  - `go/internal/query/code_cypher_test.go` — `db.labels()` → dialect
    method.
  - `go/internal/query/code_call_graph_contract_test.go` — relax string
    assertion to dialect-aware matcher.

**Telemetry obligations:**
- No new metrics. Ensure spans still record `db.statement` tag for
  both dialects.

**Tests:**
- New `graph/dialect_test.go` asserts expected string output per
  dialect for every method.
- Existing query-layer integration tests run against both backends in
  a matrix (gated by build tag until Phase 5 stabilizes).

**Exit criteria:**
- `grep -E 'apoc\\.|db\\.index\\.fulltext|db\\.labels|shortestPath\\(' go/internal | grep -v dialect` returns zero call sites outside
  the dialect implementations and their tests.
- Both dialect test suites green.

---

### Phase 5 — Profile wiring + local runtime composition (S after Phases 2 + 3, ~1 wk)

**Goal:** A single `pcg index .` command on the `local` profile boots
embedded Postgres, opens a Ladybug database, runs bootstrap-index
in-process, and prints stats.

**Pre-edit gate:**
1. Entry: `go/internal/app/app.go`, `cmd/bootstrap-index/main.go`,
   `cmd/api/main.go`, `cmd/mcp-server/main.go`, `cmd/pcg/basic.go`.
2. Phase order: Final integration step; depends on 1, 2, 3, 4.
3. Data deps: Schema applied against embedded Postgres (Phase 2),
   Ladybug `NODE TABLE` / `REL TABLE` DDL applied.
4. Re-trigger: First-run bootstrap populates both backends; subsequent
   `pcg index` picks up deltas.

**Scope:**
- Profile config in `runtime.LoadConfig`:
  - New field `StorageProfile string` (`service` | `local`).
  - Precedence: CLI flag > `PCG_STORAGE_PROFILE` env > default
    `service`.
- `runtime.OpenGraphDriver(ctx, getenv)` dispatches between
  `neo4j.NewDriver(runtime.OpenNeo4jDriver(...))` and
  `ladybug.NewDriver(...)`.
- `runtime.OpenRelationalDB` dispatches between external pgxpool and
  embedded-postgres-backed pgxpool.
- Bootstrap-index importable entry:
  `cmd/bootstrap-index/bootstrap.Run(ctx, Config) error`. `main.go`
  becomes a ≤ 20-line wrapper.
- `cmd/pcg/basic.go.runIndex` local branch calls `bootstrap.Run`
  in-process. Service branch keeps `syscall.Exec`.
- `cmd/pcg/service.go` local branch hosts API + MCP in-process and
  routes commands directly; service branch unchanged.
- `--storage-profile` flag added to `pcg index`, `pcg api start`,
  `pcg mcp start`.

**Telemetry obligations:**
- `pcg_dp_storage_profile` info metric (value=1, attribute `profile=service|local`).
- Structured log at startup: `runtime.storage_profile_selected` with
  `profile`, `graph_backend`, `postgres_mode`.

**Tests:**
- E2E smoke test in `go/test/local_profile_e2e_test.go`: `pcg index .`
  on a 2-file toy repo, assert `pcg list` returns one repository,
  assert `pcg analyze callers fn` returns expected caller.
- Contract test: service profile smoke test continues to pass byte-identically.

**Exit criteria:**
- Local-profile `pcg index .` completes on a small repo within 15
  seconds cold, 5 seconds warm.
- Service-profile CI lane unchanged.

---

### Phase 6 — Single-writer serialization + concurrency validation (S after Phase 3, ~3 days)

**Goal:** Enforce and measure single-writer behavior in the Ladybug
adapter so Ingester + Reducer + API write paths do not corrupt the
local DB.

**Pre-edit gate:**
1. Entry: Ingester + Reducer + API write sites.
2. Phase order: After Phase 3 adapter exists; before Phase 5 ships to
   users.
3. Data deps: None.
4. Re-trigger: N/A.

**Scope (updated per D3 three-layer model):**
- **Layer 3 (in-process):** `ladybug.Driver.WriteSession` acquires a
  `sync.Mutex` around every `Execute` / `ExecuteGroup`. Release on
  session Close or context cancel.
- **Layer 2 (cross-process):** adapter opens `~/.pcg/local/<hash>/write.lock`
  with `flock(LOCK_EX | LOCK_NB)` before first write; writes the
  PID + acquisition timestamp into the lockfile for diagnostics.
  Second opener gets `EWOULDBLOCK` → surfaces actionable error.
- **Layer 1 (daemon-first):** introduced in Phase 7.5 watch runtime;
  Phase 6 only builds the protocol scaffolding (unix socket path
  convention + client detection logic in a new
  `go/internal/runtime/localctl/` package). Integration lands
  alongside watch.
- Optional command-queue implementation behind a feature flag for
  perf comparison (defer if mutex is sufficient).
- Stress test — writers:
  - `T-mt-1` in-process: 3 goroutines interleaved MERGE + MATCH on
    a 100k-node DB. Assert no errors, consistent final state.
  - `T-mt-2` cross-process: two `pcg` subprocess writers against same
    data dir; second must fail fast with lockfile error; no store
    damage (verified by post-run integrity query).
  - `T-mt-3` daemon-routing: `pcg watch` running + `pcg index` writes
    → writes observed through daemon's adapter, lockfile is held by
    daemon PID only.
- Document in the adapter README: all three layers, with the failure
  mode each catches.

**Telemetry obligations:**
- `pcg_dp_ladybug_write_serialization_wait_seconds` histogram
  (already introduced in Phase 3) must show non-zero on the stress test.
- `pcg_dp_ladybug_active_writers` gauge (max 1 expected in local profile).

**Tests:**
- `ladybug/concurrency_test.go` covering simultaneous writer/reader,
  writer/writer, and reader-starvation edges.

**Exit criteria:**
- Stress test passes 100×.
- Wait-histogram p99 < 200 ms on the canonical ingester+reducer load
  pattern.

---

### Phase 7 — CLI flag plumbing + user docs (P with Phase 5, ~3 days)

**Goal:** User can discover and use the local profile from `pcg --help`
and the docs site.

**Scope:**
- `--storage-profile=local|service` global flag on root command
  propagated to all subcommands that touch storage.
- `pcg doctor` prints which profile is active, embedded Postgres
  health, Ladybug DB path and size.
- `docs/docs/getting-started/quickstart.md` gets a "Desktop mode"
  section with the `brew install pcg && pcg index .` happy path.
- `docs/docs/deployment/overview.md` gets a table comparing
  profiles (scope, latency, persistence, concurrency).
- README "Quick Start" gets a third path: **Run locally with no
  infra**.

**Exit criteria:**
- `mkdocs build --strict` clean.
- `pcg --help` lists `--storage-profile` and a one-line description.

---

### Phase 7.5 — Watch mode + dogfood runtime (S after Phase 7, ~1 wk)

**Goal:** `pcg watch .` runs live against the current repo, incrementally
re-indexes on change, and serves MCP reads in-process — enabling PCG
devs to dogfood PCG while writing PCG.

**Pre-edit gate answers:**
1. **Entry point.** `go/cmd/pcg/basic.go` gains a new `watch` subcommand
   wiring into `go/internal/app/app.go` for lifecycle.
2. **Phase ordering.** Watch depends on Phase 5 (profile wiring) and
   Phase 6 (single-writer contract) being in place. It runs BEFORE
   graduation (Phase 8) so the dogfood data never leaves local.
3. **Data dependencies.** Reads same `~/.pcg/local/` data dir the other
   local commands own. Cannot co-exist with another watch process on
   the same dir (PID lock).
4. **Re-trigger.** fsnotify events → debounced batch → incremental
   collector re-scan of affected paths → reducer → Ladybug + embedded
   PG writes → MCP readers see new generation transparently.

**Scope:**
- New runtime package `go/internal/runtime/watcher/` with:
  - `Supervisor` — owns fsnotify handle, lifecycle, PID lockfile.
  - `ChangeQueue` — debounced coalescer with max-batch cap (fallback
    to full scan on overflow, per R12).
  - `Reindexer` — in-process bootstrap-index invocation scoped to a
    path set (depends on D6 importable bootstrap).
  - `ExcludeFilter` — respects `.pcgignore` + built-in excludes; hard
    excludes data dir itself (per R10).
- New CLI: `pcg watch [path]`, `pcg watch status`, `pcg watch stop`,
  `pcg local reset` (R8, R16 escape hatch).
- Schema version file at `~/.pcg/local/schema_version` written by
  Phase 5; watch refuses to open on mismatch (R13).
- Data-dir conflict guard: absolute repo path → sha256 → per-worktree
  subdir under `~/.pcg/local/<hash>/` (R14).
- OS-resume handling: periodic PG health probe; on fail, attempt
  graceful restart before exiting watch (R15).
- **MCP readiness** (revised per codex-review finding #3): stdio
  alone is not a reusable endpoint because the client must own the
  child process. The daemon MUST expose a connectable transport so
  any MCP client can attach after `pcg watch` is already running.
  Contract:
  - Default: `pcg watch` binds MCP over **HTTP/SSE on a unix socket**
    at `~/.pcg/local/<hash>/mcp.sock` (Linux, macOS). This is the
    endpoint dogfood users point IDE/agent config at. Socket is
    mode 0600 to match CLI user ownership.
  - Also: `pcg watch` serves the same MCP surface on
    `http://127.0.0.1:<auto-port>` when `--mcp-http` is passed, for
    tooling that cannot speak unix-socket MCP.
  - Separately: `pcg mcp stdio` is a short-lived **client-spawned**
    stdio MCP process that auto-discovers and proxies to the running
    daemon socket. This is the entry Claude Code / Cursor / Windsurf
    config files actually launch, because those clients speak stdio.
  - If no daemon is running, `pcg mcp stdio` falls back to standalone
    (acquires write-lock, opens Ladybug read-only session).
  - Flag surface on `pcg watch`: `--mcp=unix|http|both|off` (default
    `unix`); `--mcp-http-port` when applicable.

**Telemetry obligations:**
- `pcg_dp_watch_events_total{kind=created|modified|deleted|skipped}`
  counter.
- `pcg_dp_watch_debounce_batch_size` histogram.
- `pcg_dp_watch_reindex_duration_seconds` histogram.
- `pcg_dp_watch_change_queue_depth` gauge.
- `pcg_dp_watch_fallback_full_scan_total` counter (R12 trigger).
- `pcg_dp_watch_lock_contention_wait_seconds` histogram (R9).
- Log keys in `contract.go`: `watch.event_received`,
  `watch.batch_coalesced`, `watch.fallback_full_scan`,
  `watch.schema_version_mismatch`, `watch.data_dir_conflict`,
  `watch.pg_resume_recovered`.
- Span names: `pcg.watch.batch`, `pcg.watch.reindex`,
  `pcg.watch.fsnotify_poll`.

**Dogfood acceptance tests (gate to GA):**
1. `git clone platform-context-graph && cd platform-context-graph &&
    pcg watch .` — starts, indexes within 60 s on dev machine.
2. Edit `go/internal/runtime/data_stores.go`, save — watch re-indexes
   the touched entities in < 2 s, spans visible.
3. `git checkout other-branch` that touches 2 000 files — watch
   coalesces, completes re-index without dropping MCP read
   availability.
4. Run `go build ./...` in the repo — `bin/` changes are ignored,
   no spurious re-index.
5. Second `pcg watch .` in another terminal — exits immediately with
   PID-lock error.
6. SIGINT to watch process — embedded PG shuts down cleanly, no
   `postmaster.pid` orphan on restart.
7. MCP query "who calls `OpenPostgres`?" from Claude Code returns a
   correct answer in < 500 ms while watch is idle.

**Exit criteria:**
- All seven dogfood tests green on macOS (ARM) + Linux (x86).
- Zero service-profile code touched (enforced by CI diff check).
- Docs: `docs/docs/guides/local-watch-mode.md` published with the
  dogfood walkthrough above.
- Risk mitigations R8–R17 each wired to a test case or
  documented-runbook entry.

---

### Phase 8 — Graduation path (`pcg export --graduate`) (P with Phase 5 finish, ~1 wk)

**Goal:** A user on `local` can move their graph + content into a
service deployment without re-indexing.

**Scope (revised per codex-review finding #4):**

`neo4j-admin database load` does NOT consume Cypher text — it only
restores a binary dump produced by `neo4j-admin database dump`. Plan
now ships **two Neo4j import paths** and the E2E test must prove
both.

- `pcg export --graduate --output dir/` writes:
  - `graph.cypher` — node + rel + index DDL as plain Cypher
    statements. Consumed by `cypher-shell -f graph.cypher` against a
    running service-profile Neo4j. Compatible with Neo4j
    Aura/clustered deployments where admin-load is not available.
  - `graph.dump` (optional, on `--format=dump`) — produced by
    streaming Cypher into a throwaway local Neo4j using
    `neo4j-admin database dump`, then emitted as the offline bulk
    format. Consumed by `neo4j-admin database load --from=graph.dump`.
    Only useful when the target supports offline load.
  - `postgres.dump` — `pg_dump -Fc` against embedded DB.
  - `manifest.json` — versions, scope identity, generation IDs,
    export format indicator.
- Documented import procedure on the service side:
  - **Default (Cypher replay)**: `cypher-shell -u $NEO4J_USER -p
    $NEO4J_PASSWORD -d neo4j -f graph.cypher`. Works against any live
    Neo4j (standalone, cluster, Aura).
  - **Offline bulk**: `neo4j-admin database load --from=graph.dump
    --database=neo4j` against a stopped Neo4j. Only when target
    ownership allows.
  - `pg_restore -d <dsn> postgres.dump` in both paths.
- End-to-end integration tests (both must pass):
  - `T-grad-1`: `local index → graduate --format=cypher → cypher-shell
    replay → pcg list` returns same repos.
  - `T-grad-2`: `local index → graduate --format=dump → neo4j-admin
    load → pcg list` returns same repos.

**Telemetry obligations:**
- Duration histogram + counter per graduation run.

**Exit criteria:**
- E2E test passes on a 5-repo fixture.
- Docs page published.

---

### Phase 9 — Hardening, cross-platform, release (S after Phases 1–8, ~1 wk)

**Goal:** `pcg` local profile ships as a supported CLI.

**Scope:**
- macOS (ARM + x86) and Linux (x86 + ARM) build matrix in CI.
- Windows parked with an explicit unsupported note (tracked in ADR
  open questions).
- Brew formula or release artifact bundling statically linked Ladybug
  + the embedded-postgres bootstrap wrapper.
- Version bump + CHANGELOG entry.
- Post-release observability review: verify dashboards differentiate
  `graph_backend=neo4j` vs `graph_backend=ladybug` cleanly.

**Exit criteria:**
- GitHub release artifact downloads and runs on a clean macOS + clean
  Ubuntu 24.04 VM end-to-end.
- Existing service deployment CI lanes green.

---

## Risk Register

| # | Risk | Phase exposed | Mitigation | Abort trigger |
| - | ---- | ------------- | ---------- | ------------- |
| R1 | Ladybug C API diverges from Kuzu; go-kuzu cgo unusable | 0, 3 | Phase 0 spike before committing | > 30% rewrite needed → reopen ADR |
| R2 | Cypher parity gaps beyond the 6 known sites | 4 | Full 552-statement replay in matrix CI | > 25 unexpected rewrites → extend schedule |
| R3 | FTS extension immature in Ladybug | 3, 4 | Start with node-level index; fall back to SQL LIKE if unusable for local profile only | FTS totally missing → accept degraded local search, document in ADR |
| R4 | Single-writer throughput bottleneck on 20-repo mono-folder | 6 | Measure during Phase 6 stress test | p99 wait > 2s → introduce command queue + re-evaluate |
| R5 | Embedded-postgres shaky on Windows | 2, 9 | Explicit Windows-deferred decision | n/a — ship macOS + Linux only |
| R6 | Ladybug abandonware risk inside 6 months | All | Quarterly upstream activity review; keep Neo4j path primary | Stale > 6 months → freeze adapter, route users to service |
| R7 | Test matrix duplication cost grows unbounded | 1, 3, 4 | Interface-level contract tests, not adapter-per-adapter | Maintenance noise > 20% of PR cost → consolidate |
| R8 | Zombie embedded-postgres subprocess after crashed `pcg watch` holds PGDATA lock | 2, Watch | Stale-pidfile detection on start; `postmaster.pid` reconciliation; orphan-reaper on first-run recovery | Recovery fails → clear guidance to `pcg local reset` |
| R9 | Two `pcg` processes (watch + CLI) race on same data dir | Watch | PID lockfile at `~/.pcg/local/watch.pid`; CLI queries acquire read-only Ladybug session; writes route through watch or hard-fail with actionable error | Lockfile corruption → fsync + atomic rename; nuke-and-retry runbook |
| R10 | Self-index loop — watch triggers on pcg's own bin/, build artifacts, embedded PGDATA | Watch | Built-in excludes: `bin/`, `dist/`, `.pcg/`, `*.test`, `*.out`, `.pcg/local/pg/`; refuses to start if data dir is inside watched tree | Exclude miss → panic fast + log which path triggered |
| R11 | Editor swap files cause churn burst (vim `.swp`, jetbrains `___jb_*`) | Watch | Name-pattern filter at fsnotify layer before debounce queue | Unknown pattern slips through → one-line regex addition |
| R12 | Massive change burst (git checkout 50k files, rebase, branch switch) | Watch | Debounced coalescer with max-batch cap; if cap exceeded, fall back to full discovery scan instead of per-file path | Scan exceeds 30s → surface progress + keep serving reads from prior generation |
| R13 | Dev rebuilds pcg while watch is running → binary upgrade mid-flight; on-disk format skew | Watch, 9 | Schema version written to data dir; mismatched version refuses to open, surfaces `pcg local migrate` | Cannot migrate → `pcg local reset` with explicit consent |
| R14 | Multiple git worktrees of same repo → same `~/.pcg/` collision | Watch, 5 | Data-dir path keyed on repo root absolute path + worktree id; or explicit `--data-dir` flag | Overlap detected → refuse to start, print conflicting worktree path |
| R15 | OS sleep/resume kills PG subprocess, leaves Ladybug lock stale | Watch | Health probe re-establishes PG on resume; Ladybug lock is in-process mutex so dies with parent | Health probe loop > 3 fails → surface and exit watch cleanly |
| R16 | Dogfood regression: buggy local adapter corrupts developer's own PCG graph | All local | `pcg local` data dir is disposable by design; `pcg local reset` one-shot; CI forbids any mutation under `~/.pcg/` from service profile | Corruption detected → reset + re-watch; dogfood data never load-bearing |
| R17 | `pcg watch` held open, MCP read queries starve under single-writer | Watch, 6 | Ladybug reads are parallel (mutex only guards writes); verify contract test; measure reader-vs-writer starvation under simulated save burst | p99 read during write burst > 500 ms → introduce per-query timeout + surface |

---

## Verification Gates (must pass before merging)

Codex-review finding #5: the earlier gate list was too narrow for a
runtime/storage change that claims "zero behavioral regressions" and
"byte-identical" service output. The gates below are the minimum set;
phase-specific scopes add more in each phase's Exit criteria.

**1. Go correctness gates** (identical to CLAUDE.md canonical):

```bash
cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server ./internal/query ./internal/mcp -count=1
cd go && go test ./internal/parser ./internal/collector/discovery ./internal/content/shape ./internal/collector -count=1
cd go && go test ./internal/terraformschema ./internal/relationships -count=1
cd go && go test ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer ./internal/runtime ./internal/status ./internal/storage/postgres -count=1
```

**2. Go lint** (new — required by the repo's golangci-lint policy for
any Go change):

```bash
cd go && golangci-lint run --timeout=5m ./...
```

**3. Production-untouched build gate** (new — enforces D10 + the
production-untouched guarantee at CI time):

```bash
# Service-only build MUST succeed without pcg_local tag.
cd go && go build -o /tmp/pcg-service ./cmd/pcg ./cmd/api ./cmd/mcp-server \
  ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer
cd go && go test ./... -count=1   # no -tags, default build
```

**4. Local-profile gate** (only when `-tags=pcg_local`):

```bash
cd go && go test ./internal/storage/graph ./internal/storage/ladybug \
  ./internal/app/localpg ./internal/runtime/watcher \
  ./internal/runtime/localctl -count=1 -tags=pcg_local
cd go && go test ./test/local_profile_e2e -count=1 -tags=pcg_local,e2e_local
```

**5. Docs gate**:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

**6. Deployment shape gate** (new — prevents runtime-shape regression):

```bash
helm lint ./deploy/helm/platform-context-graph
helm template platform-context-graph ./deploy/helm/platform-context-graph \
  | kubectl apply --dry-run=client --validate=true -f -
docker compose --profile workflow-coordinator config -q
docker compose config -q
```

**7. Whitespace gate**:

```bash
git diff --check
```

**8. Service-profile regression smoke** (CLAUDE.md reminder): a full
E2E run on the remote 896-repo instance before flipping Phase 9 to
GA. Must observe identical repository/entity counts, identical
metric names, and identical Cypher query plans for a representative
query set against the pre-merge baseline.

---

## Telemetry Additions Summary

| Metric | Type | Phase | Purpose |
| ------ | ---- | ----- | ------- |
| `pcg_dp_storage_profile` | info gauge | 5 | Which profile is active |
| `pcg_dp_local_postgres_boot_seconds` | histogram | 2 | Embedded PG cold/warm boot cost |
| `pcg_dp_local_postgres_running` | gauge | 2 | Liveness |
| `pcg_dp_ladybug_query_duration_seconds` | histogram | 3 | Ladybug query latency |
| `pcg_dp_ladybug_write_serialization_wait_seconds` | histogram | 3, 6 | Single-writer contention |
| `pcg_dp_ladybug_active_writers` | gauge | 6 | Concurrency invariant (max 1) |
| `graph_backend` attribute on existing metrics | label | 1 | Profile-aware dashboards |

New log keys in `telemetry/contract.go`:

- `local_postgres.booted`
- `runtime.storage_profile_selected`
- `ladybug.serialization_wait_exceeded`
- `graduation.completed`

---

## Milestone Calendar

| Week | Phases shipping | Demonstrable outcome |
| ---- | --------------- | -------------------- |
| 1 | 0 + start 1 | Spike proves Ladybug + go-kuzu can answer a PCG-style query |
| 2 | 1 complete | Neo4j adapter behind `graph.Driver`; all tests green |
| 3 | 2 + 3 in parallel | Embedded Postgres boots; Ladybug adapter passes contract tests |
| 4 | 4 | Dialect rewrites in main branch |
| 5 | 5 + 6 | `pcg index .` local profile E2E green; single-writer validated |
| 6 | 7 + 7.5 | Docs + `pcg watch .` dogfood runtime live |
| 7 | 8 | Graduation path (local → service) |
| 8 | 9 | Cross-platform release candidate |

---

## Open Questions Carried From ADR

1. Postgres version pin for embedded distribution. Proposed: 16.x LTS.
2. Windows cgo support timeline. Proposed: defer post-v1.
3. FTS extension load story in the bundled Ladybug build.

Each question gets resolved in the phase that exposes it, not at
planning time.

---

## Appendix: Files Expected To Change

Edit:
- `go/internal/runtime/data_stores.go` — profile seam (Phase 5)
- `go/internal/app/app.go` — lifecycle extension (Phase 5)
- `go/internal/storage/neo4j/*.go` — refactor to `graph.Driver` (Phase 1)
- `go/internal/query/neo4j.go` → `graph_reader.go` (Phase 1)
- `go/internal/graph/schema.go` — dialect-aware FTS (Phase 4)
- `go/internal/query/impact.go` — dialect-aware shortest path (Phase 4)
- `go/internal/query/code_call_chain.go` — dialect-aware shortest path (Phase 4)
- `go/cmd/pcg/basic.go` — local-profile in-process bootstrap (Phase 5)
- `go/cmd/pcg/service.go` — local-profile in-process API/MCP (Phase 5)
- `go/cmd/bootstrap-index/main.go` — extract `Run(ctx, cfg)` entry (Phase 5)
- `go/internal/telemetry/contract.go` — new dimension keys + log keys (Phases 1, 2, 3)
- `go/internal/telemetry/instruments.go` — new metrics (Phases 2, 3, 6)
- `docs/docs/getting-started/quickstart.md` — desktop-mode section (Phase 7)
- `docs/docs/deployment/overview.md` — profile comparison table (Phase 7)
- `README.md` — third quick-start path (Phase 7)

Create:
- `go/internal/storage/graph/` — interface pkg (Phase 1)
- `go/internal/storage/graph/dialect.go` (Phase 4)
- `go/internal/storage/ladybug/` — adapter pkg (Phase 3)
- `go/internal/app/localpg/` — embedded PG wrapper (Phase 2)
- `third_party/go-ladybug/` — cgo binding (Phase 3)
- `go/test/local_profile_e2e_test.go` (Phase 5)
- `docs/docs/deployment/desktop-mode.md` (Phase 7)
- `go/internal/runtime/watcher/` — supervisor, change queue, reindexer,
  exclude filter (Phase 7.5)
- `go/cmd/pcg/watch.go` — `pcg watch` / `pcg local reset` / `pcg
  watch status` commands (Phase 7.5)
- `docs/docs/guides/local-watch-mode.md` — dogfood walkthrough (Phase 7.5)
- CI workflow step `build-service-only` — compiles without `pcg_local`
  tag to enforce production-untouched invariant (Phase 9)

Delete: none. Both profiles remain first-class.
