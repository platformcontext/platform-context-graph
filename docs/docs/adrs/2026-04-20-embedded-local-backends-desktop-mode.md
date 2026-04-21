# ADR: Embedded Local Backends For PCG Desktop Mode

**Date:** 2026-04-20
**Status:** Proposed
**Authors:** Allen Sanabria
**Deciders:** Platform Engineering
**Related:**

- `README.md` runtime model (API / MCP / Ingester / Reducer / Bootstrap Index)
- `CLAUDE.md` — Runtime Contract, Facts-First Flow

---

## Context

The current PCG platform runtime is a Go-owned, multi-runtime service that
mandates **external Neo4j + external Postgres**. Every public CLI verb
(`pcg index`, `pcg list`, `pcg stats`, `pcg analyze …`, `pcg query`) is
either a direct writer into those stores (via `pcg-bootstrap-index`) or an
HTTP client against `pcg-api`, which itself requires both. There is no
embedded, zero-infra path today.

Up to and including the Python runtime that this codebase evolved past, PCG
supported two lightweight local backends:

1. **KuzuDB** — embedded, single-process, Cypher-compatible.
2. **FalkorDB** — Redis-module graph DB, Cypher-compatible.

Both are unavailable in their original form on 2026-04-20:

| Historical option | Status |
| --- | --- |
| KuzuDB (`kuzudb/kuzu`) | Archived by upstream Oct 2025. Official `go-kuzu` binding archived alongside it. |
| FalkorDB | Server under SSPLv1. `FalkorDBLite` embedded bundle ships for Python and TypeScript only — no Go bundle. |

This ADR decides which embedded backend PCG adds for a **desktop / local-only
mode** that does not require Docker Compose, external Neo4j, or external
Postgres. The production contract (external Neo4j + external Postgres) does
not change — this is purely additive.

### Why A Desktop Mode

PCG has three distinct audiences:

1. **Solo developers and AI-tool users** — want `brew install pcg && pcg
   index .` with an IDE/agent MCP connection. Allergic to standing up
   Neo4j + Postgres.
2. **Team / platform engineers** — Docker Compose or Kubernetes with
   shared Neo4j + Postgres. Today's default path.
3. **CI / ephemeral environments** — want a disposable backend, no
   external dependencies, fast startup.

Audiences (1) and (3) are currently locked out. That directly limits
adoption of the MCP and CLI surfaces PCG already ships.

### What This ADR Decides

1. That PCG adds a first-class `local` storage profile distinct from the
   `service` profile that wires external Neo4j + external Postgres.
2. Which graph backend to use in `local` mode.
3. Which Postgres-compatible backend to use in `local` mode.
4. The storage abstraction boundary in `go/internal/storage/`.
5. Which CLI flags and environment variables switch modes.
6. That the local mode supports **all indexing scopes** (single repo,
   mono-folder / workspace, and cross-repo) — scope is orthogonal to
   storage.

### What This ADR Does Not Decide

- It does not change the production deployment contract.
- It does not remove Neo4j + Postgres support.
- It does not rewrite any Cypher the canonical graph schema emits.
- It does not introduce a new query language.
- It does not introduce a separate single-repo-only fallback backend.
  Early research considered Apache AGE, but its quantified performance
  (see below) rules it out across PCG's expected scopes.

---

## Problem Statement

Pick the lightest, most maintainable embedded backend pairing that can host
the PCG canonical graph plus facts/queue/content store on a single developer
laptop with zero external services. Preserve Cypher on the graph side and
preserve PCG's existing Postgres feature usage on the relational side so
that no existing adapter in `go/internal/storage/postgres` has to be
rewritten.

Hard constraints:

- MUST preserve Cypher as the canonical graph query surface. The entire
  `go/internal/graph` + API read layer speaks Cypher today.
- MUST be permissively licensed (Apache-2.0, MIT, BSD). **No SSPL, no
  BSL, no AGPL** on core runtime dependencies.
- MUST have working Go integration in 2026 (native, cgo, or first-party
  Go SDK). Taking on fork-and-port work for a Python-only library is
  disallowed.
- MUST support PCG's real scope: a 20-repo mono-folder must not be a
  failure mode. Reference point: PCG production runs 878+ repos; one
  mono-folder is a small fraction of that but already produces millions
  of edges.
- MUST support PCG's existing Postgres features: LISTEN/NOTIFY for the
  work queue, advisory locks, JSONB columns.
- SHOULD NOT require installing Postgres or Neo4j by hand.
- SHOULD ship inside PCG's existing binaries — no separate sidecar the
  user has to manage.

Soft goals:

- Fast cold-start (`pcg index .` usable in seconds on first run).
- A concrete "graduate this index to the shared service" story so users
  are not trapped in local mode.

---

## Options Considered

### Graph side

#### Ladybug (`LadybugDB/ladybug`)

- Kuzu fork, MIT, C++ core, columnar + vectorized execution, Cypher.
- Maintainer: Arun Sharma (ex-Facebook, ex-Google) plus community
  contributors.
- Activity on 2026-04-20: 979 stars, 72 forks, active commit log — most
  recent commit same day (`Preserve correlated rel scan orientation
  during join planning`). Issues enabled, 72 open.
- Inherits Kuzu's LDBC-SF100 benchmarks: 280M nodes / 1.7B edges on a
  single machine; 9ms path-query class.
- Go binding path: cgo wrapper of the Ladybug C API. The archived
  `go-kuzu` binding is a ready starting point; Ladybug preserves Kuzu's
  public C API.
- **Decision: selected.**

#### Bighorn (`Kineviz/bighorn`)

- Kuzu fork, MIT, announced at the same time as Ladybug.
- Activity on 2026-04-20: 124 stars, 7 forks, `has_issues: false`, last
  push 2025-10-11 (six months stale). Commit log is README and logo
  changes plus one unrelated C++ patch, all pre-Oct-11.
- **Decision: rejected** — announcement-only; no evidence of sustained
  maintenance. Revisit only if upstream activity resumes.

#### Apache AGE

- Postgres extension, Apache-2.0, openCypher, would reuse the existing
  Postgres storage path.
- Quantified failure modes:
  - Edge import: 2,600 of 674,103 edges in 2 hours (`apache/age`
    discussion #130).
  - Node creation at scale: 7.6M-row build → ~24 hours
    (`apache/age` issue #1287).
  - Variable-length path query scaling: 7s → 3.5min → 7min as hops
    grow (`apache/incubator-age` issue #195).
- Architectural cause: openCypher compiled to SQL joins; join-explosion
  is inherent to the approach.
- PCG's mono-folder and workspace scopes produce millions of edges.
  AGE reaches its failure regime inside a single mono-folder.
- **Decision: rejected** across all scopes for this ADR. Not pursued as
  a single-repo-only fallback either — maintaining a second graph
  adapter for a narrow slice is not worth the ongoing test matrix.

#### FalkorDB / FalkorDBLite

- Core server under SSPLv1. Embedded `FalkorDBLite` bundle ships only
  for Python and TypeScript; no Go path. SSPL is incompatible with
  PCG's current positioning, and PCG will not build a Go embedded
  bundle on top of a copyleft core.
- **Decision: rejected.**

#### SurrealDB

- Apache-2.0, embeddable, first-party Go SDK.
- Query language is SurrealQL. Cypher is not supported. Adopting it
  would double PCG's graph query surface — every Cypher read and write
  path would need a parallel implementation or a translation layer PCG
  does not own.
- **Decision: rejected** on the "preserve Cypher" hard constraint.

#### GoraphDB (`mstrYoda/goraphdb`)

- Pure-Go, single-author experimental project, 82 stars, no releases.
- Roadmap-heavy: advertised production features exist as scaffolding.
  Cypher subset lacks aggregations and large parts of expression
  evaluation. No benchmarks beyond an M-series laptop anecdote.
- **Decision: rejected for core.** Could inform a future pure-Go
  adapter but is not a bet PCG should take on today.

#### DuckDB / SQLite (graph-on-SQL)

- Permissive, excellent Go bindings, no Cypher. Would require PCG to
  write and maintain a Cypher-to-SQL translator.
- **Decision: rejected** on the "preserve Cypher" constraint.

### Postgres side

#### `fergusstrange/embedded-postgres`

- Go library that downloads and runs a real Postgres binary (Postgres
  16/17) under the PCG process's lifecycle.
- Wire- and SQL-compatible because it is actual Postgres. All PCG
  usage continues to work: LISTEN/NOTIFY for queue, advisory locks,
  JSONB, any pgx-specific feature.
- Zero changes to `go/internal/storage/postgres`.
- Footprint: ~50 MB per-arch binary extracted to `~/.pcg/postgres`,
  boot ~2s first time, <1s subsequent starts.
- Apache-2.0 library; bundled Postgres is PostgreSQL license.
- **Decision: selected.**

#### SQLite

- Native Go driver, tiny footprint.
- Not wire-compatible with Postgres. Missing LISTEN/NOTIFY, advisory
  locks, JSONB semantics. Adopting it requires forking every queue,
  lock, and JSONB code path in PCG and maintaining a second SQL adapter
  forever.
- **Decision: rejected.**

#### CockroachDB single-node

- Postgres wire protocol.
- Needs a separate binary install and cluster init. Not "embedded"
  in any practical sense. Adds operational surface (certificates, init
  flows) even in local mode.
- **Decision: rejected.**

#### pglite (Postgres compiled to WASM)

- No first-class Go binding in 2026. Primary audience is the JS
  ecosystem.
- **Decision: rejected.**

#### DuckDB

- Not Postgres wire-compatible. Same adapter-rewrite problem as SQLite.
- **Decision: rejected.**

#### "Just `brew install postgresql`"

- Feasible for power users but defeats the "zero-install" goal for
  audience (1) and (3).
- **Decision: kept as an explicit opt-out.** If `PCG_POSTGRES_DSN` is
  already set, PCG uses that Postgres instead of starting embedded
  Postgres. Power users keep their existing setup.

---

## Decision

Adopt exactly two components for the new `local` storage profile:

1. **Graph backend: Ladybug**, embedded in-process via a cgo adapter in
   `go/internal/storage/ladybug`. Ladybug inherits Kuzu's Cypher surface
   and scale profile, which covers all indexing scopes PCG supports
   today.
2. **Postgres backend: real Postgres via
   `fergusstrange/embedded-postgres`**, started as a subprocess under
   `pcg`'s lifecycle. The existing `go/internal/storage/postgres` package
   is unchanged.

No secondary graph backend. Apache AGE, Bighorn, and every other option
evaluated above are explicitly rejected for the reasons documented. The
community is revisited in six months and this ADR is superseded only if a
second backend becomes demonstrably mature.

### Desktop-mode Topology

```text
pcg (CLI)
  │
  ├── pcg-bootstrap-index / pcg-api / pcg-mcp-server  (in-process)
  │     │
  │     ├── Ladybug            ← graph (in-process, cgo)
  │     └── pgx → Postgres     ← facts / queue / content
  │
  └── fergusstrange/embedded-postgres
        └── Postgres binary managed by pcg (subprocess)
```

The production-service topology (`Service Runtimes` table in `README.md`)
is unchanged.

### Scope Coverage

`pcg index`, `pcg workspace sync`, and `pcg workspace index` all accept the
`local` profile identically. Storage is orthogonal to scope:

| Scope | Fact volume | Ladybug verdict |
| --- | --- | --- |
| One small repo | ~10k nodes / ~30k edges | trivial |
| One large monorepo | ~500k nodes / ~2M edges | seconds |
| 20-repo mono-folder | ~2M nodes / ~10M edges | seconds |

A future ADR may tighten PCG's heuristics (e.g., sharding very large
workspaces), but no scope is locked out of desktop mode at adoption.

### Mode Switching

Add one environment variable and one CLI flag:

- `PCG_STORAGE_PROFILE=local|service`. Default `service` preserves
  today's behavior. `local` swaps graph writes to Ladybug and starts
  embedded Postgres if no external DSN is set.
- `--storage-profile=local|service` on `pcg index`, `pcg api start`,
  `pcg mcp start`.

If `PCG_POSTGRES_DSN` is set while `PCG_STORAGE_PROFILE=local`, PCG uses
that Postgres and does not boot embedded-postgres.

External Neo4j is never started in `local` mode. The graph store is
Ladybug, end of story.

---

## Consequences

### Positive

- A real `brew install pcg && pcg index .` path for solo developers, AI
  tool users, and CI.
- Preserves Cypher everywhere. No query-layer rewrite.
- Reuses `go/internal/storage/postgres` without changes.
- Permissive licenses throughout — MIT (Ladybug), Apache-2.0
  (embedded-postgres wrapper), PostgreSQL license (the Postgres binary).
- Mono-folder and workspace scopes are real in desktop mode, not
  second-class.

### Negative

- One new cgo dependency to build and cross-compile. Windows in
  particular will need clear build instructions for Ladybug.
- PCG ships a bundled Postgres binary in `~/.pcg/postgres` on first
  `local`-profile run. Disk footprint ~50 MB per architecture, first
  boot ~2s.
- Ladybug is young as an independent project. PCG accepts maintenance
  risk and monitors it quarterly.
- Two supported graph backends in the codebase (Neo4j for service,
  Ladybug for local). Parity tests are mandatory.

### Migration / Graduation

`pcg export --graduate` dumps the local graph to Cypher statements and the
facts/queue/content store to a Postgres dump compatible with the service
profile. This prevents the local profile from trapping users who later
want to move to the shared Neo4j + Postgres deployment.

---

## Implementation Outline

1. **Storage abstraction**
   - Extract the current Neo4j-shaped interfaces in
     `go/internal/storage/neo4j` into an interface package
     (`go/internal/storage/graph`).
   - Implement the interface twice: existing Neo4j driver (service
     profile), new Ladybug adapter (local profile).

2. **Ladybug adapter (`go/internal/storage/ladybug`)**
   - cgo bindings against Ladybug's C API. Start from the archived
     `go-kuzu` binding layout and retarget to the Ladybug library.
   - Map the PCG write contract (batch node/edge inserts, upsert,
     parameterized Cypher) onto Ladybug.
   - Expose a read session type that mirrors the existing Neo4j session
     surface used by `go/internal/query`.

3. **Embedded Postgres boot (`go/internal/app/localpg`)**
   - Wrap `fergusstrange/embedded-postgres`. Pin version. Place data in
     `~/.pcg/postgres` or a user-overridable path.
   - Run `postgres.ApplyBootstrap` (the existing migration path) after
     first start.
   - Shut down cleanly on process exit.

4. **Runtime profile wiring (`go/internal/app`)**
   - Branch on `PCG_STORAGE_PROFILE` once during runtime startup. Build
     either the service wiring (Neo4j + external Postgres) or the local
     wiring (Ladybug + embedded Postgres).
   - Keep the branching at a single seam — no per-feature "is local?"
     flags scattered through the code.

5. **CLI wiring (`go/cmd/pcg`)**
   - Honor `--storage-profile` and `PCG_STORAGE_PROFILE` on
     `pcg index`, `pcg api start`, `pcg mcp start`.
   - When the CLI runs `pcg-bootstrap-index` via `exec`, pass the
     profile through as an environment variable.

6. **Parity tests**
   - A single matrix in `go/internal/storage` runs the PCG Cypher query
     set against Neo4j and Ladybug. Any divergence fails CI.

7. **Graduation**
   - `pcg export --graduate` writes a `cypher.dump` + `pg_dump` pair the
     service profile can import.

8. **Docs**
   - New `docs/docs/guides/desktop-mode.md` — `local` profile, scopes
     covered, graduation path, known limitations.
   - Update `docs/docs/getting-started/quickstart.md` to offer a
     no-Compose path once this lands.
   - Update `README.md` Runtime Model to mention the `local` profile
     as additive.

---

## Open Questions

1. Which Postgres version does `fergusstrange/embedded-postgres` pin that
   best matches the production runtime? Pick one and declare it in this
   ADR's addendum once implementation starts.
2. Does Ladybug's cgo build work cleanly on Windows without the
   MSYS2/UCRT64 hoop? If not, the Windows story for local mode is
   "install WSL" and that needs to be documented.
3. What is the minimum Cypher surface PCG emits? An inventory in
   `go/internal/graph` + `go/internal/query` bounds the Ladybug porting
   and parity-test effort; produce it as the first implementation task.
