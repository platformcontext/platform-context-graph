# Implementation Plan: Local Code Intelligence Host, Authoritative Graph Mode, And Backend Conformance

**Date:** 2026-04-20
**Owner:** Allen Sanabria
**Tracks ADR:** `2026-04-20-embedded-local-backends-desktop-mode.md`
**Status:** In Progress (Chunks 1-3 shipped, Chunk 3.5 in progress)

**Companion Specs:**

- `docs/docs/reference/capability-conformance-spec.md`
- `docs/docs/reference/truth-label-protocol.md`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/dead-code-reachability-spec.md`
- `docs/docs/reference/fact-schema-versioning.md`
- `docs/docs/reference/plugin-trust-model.md`
- `docs/docs/reference/local-performance-envelope.md`
- `docs/docs/reference/local-host-lifecycle.md`

---

## Chunk Status

This table reflects the current branch state, including active working-tree
slices in the current PR. It MUST be updated in the same PR that changes
chunk-visible code. Drift between this table, the working tree, and
verification evidence = reviewer rejects PR.

| Chunk | Title | Status | Evidence | Remaining |
| --- | --- | --- | --- | --- |
| 1 | Capability contract + truth labels | Shipped | `488ff808`, `35a3a091` | — |
| 2 | Capability ports (`GraphQuery`, `ContentStore`) | Shipped | `08795558`, `07619013`, `085c91a3` | — |
| 3 | Lightweight local host | Shipped | `a3e05ecf`, `c832a84c`, current branch local-host supervisor + embedded Postgres lifecycle | perf-envelope smoke evidence still needs to be attached to the PR |
| 3.5 | NornicDB laptop sidecar + `local_authoritative` profile | In progress | `0e4d8a5f`, current branch profile/backend and runtime-gating slices, `da35d729`, current branch authoritative sidecar lifecycle + shared Bolt-driver path + graph-aware reclaim, manual smoke with `/tmp/nornicdb-headless` showing healthy owner + clean Ctrl-C shutdown, current branch binary verification + random workspace credentials, `575ca864` opt-in syntax/workaround gates, `5f5a781e` schema-dialect router + `TestNornicDBSchemaAdapterVerification` pass, current branch `pcg install nornicdb --from <path>` local-file installer with managed `${PCG_HOME}/bin/nornicdb-headless` discovery, current branch `pcg graph logs` workspace log reader, current branch owner-aware `pcg graph stop`, current branch foreground `pcg graph start` local-host shortcut, current branch stopped-owner `pcg graph upgrade --from <path>`, 2026-04-22 smoke with temporary `PCG_HOME=/tmp/pcg-local-authoritative-smoke` proving install → start → status running → logs → stop → status stopped, 2026-04-23 smoke with `PCG_HOME=/tmp/pcg-local-authoritative-e2e2` proving MCP `search_file_content` and `find_code` return real repo results from the content index while NornicDB canonical graph projection times out and reports degraded status, current branch NornicDB grouped-write capability router with `PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` reserved for conformance | release-backed download/signature installer, perf-envelope smoke |
| 4 | Authoritative graph analysis hardening | Not started | — | all |
| 5 | Backend conformance suite | Not started | — | all |
| 5b | NornicDB conformance across profiles | Not started | — | matrix run vs `local_authoritative`, `local_full_stack`, `production`; PCG-workload perf comparison vs Neo4j baseline |
| 6 | OCI collector plugin contract | Not started | — | all |
| 7 | Neo4j deprecation path (contingent on 5b pass) | Not started | — | dual-backend operation docs, migration tooling Neo4j → NornicDB, deprecation window + default flip |

---

## Executive Summary

This plan implements a local-first developer workflow without creating a second
authoritative graph product.

The work is organized around one principle:

- lightweight local mode should be excellent for code lookup and code
  comprehension
- authoritative graph truth should remain owned by the full local stack and
  production runtime path

The implementation is therefore split into six chunks:

1. define the capability contract and truth labels
2. make query surfaces depend on capability ports instead of backend brands
3. ship the lightweight local code-intelligence host
4. harden authoritative graph-backed code analysis in full local stack and prod
5. add backend conformance testing before any new graph backend is declared
   supported
6. add OCI-packaged collector plugin seams at the fact-emission boundary

This keeps production risk bounded while still giving developers the local
stdio MCP workflow they want.

## Success Criteria

### Developer experience

- a developer can install one `pcg` binary and use local stdio MCP without
  Docker for code-intelligence queries
- local mode supports single-repo and monofolder indexing
- local mode is explicit when an answer is `exact`, `derived`, or `fallback`

### Production safety

- the deployed runtime contract remains split by ownership
- no production query or reducer feature regresses because of local-mode work
- service-profile runtime tests continue to pass unchanged

### Architecture

- API, MCP, projector, reducer, and query layers depend on capability ports
  instead of concrete backend brands where practical
- backend conformance tests exist before any alternate graph backend is called
  supported

### Extensibility

- new collectors can be packaged as OCI artifacts and emit facts through a
  stable plugin contract

---

## Query Capability Matrix

This matrix is the contract the implementation should target.

| Capability | Lightweight local | Full local stack | Production |
| --- | --- | --- | --- |
| Exact symbol lookup | Yes | Yes | Yes |
| Fuzzy symbol search | Yes | Yes | Yes |
| Variable lookup | Yes | Yes | Yes |
| Code / comment / docstring search | Yes | Yes | Yes |
| Decorator / annotation search | Yes | Yes | Yes |
| Argument-name search | Yes | Yes | Yes |
| Methods on class | Yes | Yes | Yes |
| Import / reference discovery | Yes | Yes | Yes |
| Inheritance / implementation discovery | Yes, when semantic facts suffice | Yes | Yes |
| Complexity and hotspot queries | Yes | Yes | Yes |
| Direct callers / callees | Derived or exact only if proven | Yes | Yes |
| Transitive callers / callees | No promise unless authoritative graph exists | Yes | Yes |
| Call-chain path tracing | No promise unless authoritative graph exists | Yes | Yes |
| Dead code | No promise unless authoritative graph exists | Yes | Yes |
| Code + infra blast radius | Limited | Yes | Yes |

---

## Chunk 1: Capability Contract And Truth Labels

### Goal

Define the product contract before changing more runtime behavior.

### Work

- introduce common truth labels across CLI, MCP, and HTTP:
  - `exact`
  - `derived`
  - `fallback`
- add one shared truth-level type and response field rather than scattered
  prose-only fallback strings
- define a structured unsupported-capability error for high-authority queries
  that lightweight local mode cannot answer correctly
- document which queries belong to:
  - `CodeSearch`
  - `SymbolGraph`
  - `CallGraph`
  - `CodeQuality`
  - `PlatformImpact`
- update API/MCP/CLI docs to reflect capability semantics rather than backend
  assumptions

### Likely touch points

- `docs/docs/why-pcg.md`
- `docs/docs/reference/http-api.md`
- `docs/docs/guides/mcp-guide.md`
- `docs/docs/reference/truth-label-protocol.md`
- `docs/docs/reference/capability-conformance-spec.md`
- `specs/capability-matrix.v1.yaml`
- `go/internal/query/openapi*.go`
- MCP tool descriptors and response payload structs

### Verification

- focused query/API tests for new truth labels
- strict docs build

---

## Chunk 2: Capability Ports Instead Of Backend Brands

### Goal

Reduce direct dependency on `Neo4jReader` and backend-specific wiring in the
read path.

These ports do not exist today as named interfaces. This chunk is net-new
interface extraction, not a move to an already-portable design.

### Work

- extract or tighten the read-side storage-seam interfaces first:
  - `GraphQuery`
  - `ContentStore`
- keep higher-order capability groupings such as `CodeSearch`,
  `SymbolGraph`, and `CallGraph` as follow-on interfaces only if adapter
  tests show that the storage-seam ports are too coarse
- move API and MCP construction toward these ports rather than concrete backend
  readers
- keep the existing service runtime behavior the same while making backend
  swaps a wiring concern
- keep wire compatibility by supporting parallel old/new wiring during the
  extraction until contract tests prove equivalence

### Shared-state and concurrency considerations

- do not widen transaction scope accidentally while extracting interfaces
- keep graph writes and relational writes owned by their existing runtimes
- preserve reducer/projector ordering and current queue contracts

### Likely touch points

- `go/cmd/api/wiring.go`
- `go/cmd/mcp-server/wiring.go`
- `go/internal/query/*.go`
- `go/internal/projector/*.go`
- `go/internal/reducer/*.go`
- `go/internal/storage/*`

### Verification

- `cd go && go test ./internal/query ./cmd/api ./cmd/mcp-server -count=1`
- `cd go && go vet ./internal/query ./cmd/api ./cmd/mcp-server`
- contract tests proving old and new wiring return the same response shape

---

## Chunk 3: Lightweight Local Code Intelligence Host

### Goal

Ship a single-binary local host that gives developers a strong stdio MCP and
CLI story without requiring Docker.

### Work

- manage embedded local Postgres lifecycle inside `pcg`
- add a local host mode used by `pcg watch`, `pcg mcp stdio`, and local query
  commands
- persist local index state under a stable per-workspace data root
- define the local data-root spec: layout, version file, ownership lock,
  migration rules, and reset behavior
- support:
  - single repo
  - monofolder / multi-repo workspace
- expose the local code-intelligence tier:
  - definitions
  - search
  - methods
  - imports
  - inheritance where semantic facts suffice
  - complexity

### Workflow shape

1. file change or initial index enters local host
2. collector parses and emits facts
3. projector writes content/entity/search-support tables
4. query surfaces read those tables directly
5. stdio MCP serves the same query contract as CLI/API

### Shared-state inventory

- local Postgres data directory
- workspace ownership record
- local status/report state
- content/entity/query-support relational tables

### Concurrency plan

- one local host process owns the workspace data root
- second invocations use a lock protocol with stale-lock recovery and fail-fast
  behavior when safe attachment is not possible
- fsnotify events are debounced and coalesced to avoid parse storms
- collector and projector work stay bounded with explicit backpressure
- child runtime shutdown must be coordinated and observable
- no orphaned embedded Postgres process on `SIGINT` or host shutdown
- embedded Postgres crash recovery and stale data-root ownership must be
  exercised explicitly

### Telemetry

- local host lifecycle spans
- local Postgres startup/shutdown logs
- query truth-level counters
- local index freshness and queue/status metrics where applicable

### Likely touch points

- `go/cmd/pcg/*.go`
- `go/internal/runtime/*.go`
- `go/internal/storage/postgres/*.go`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/reference/local-performance-envelope.md`
- local MCP startup and discovery code

### Verification

- focused CLI/runtime tests
- local lifecycle tests for clean shutdown
- perf-envelope smoke tests against the documented local targets
- manual smoke test for `pcg watch .` + `pcg mcp stdio`

---

## Chunk 3.5: NornicDB Laptop Sidecar And `local_authoritative`

### Goal

Add an explicit authoritative-local runtime contract without silently turning
it into lightweight mode.

### Work

- add `local_authoritative` runtime selection to the local host
- default laptop graph discovery and future install flow to
  `nornicdb-headless`, while allowing explicit opt-in to the larger full
  `nornicdb` binary
- persist profile and graph-backend metadata in `owner.json`
- reserve graph-sidecar paths inside the local workspace data root
- fail loudly when `local_authoritative` is requested before the graph sidecar
  lifecycle is wired
- add the graph-sidecar startup, health, and shutdown lifecycle behind the
  local host once the NornicDB adapter is ready
- add the first installer slice:
  `pcg install nornicdb --from <path> [--sha256 <hex>] [--force]`, which
  verifies a local binary, copies it to `${PCG_HOME}/bin/nornicdb-headless`,
  and records a managed install manifest without yet downloading release
  artifacts

### First implementation slice

- add `graph/` to the local workspace layout
- add `profile`, `graph_backend`, and graph-sidecar metadata fields to
  `owner.json`
- make the local host resolve `PCG_QUERY_PROFILE` and `PCG_GRAPH_BACKEND`
  explicitly instead of hardcoding lightweight mode
- reject unsupported `local_authoritative` startup before workspace ownership
  or embedded Postgres boot so the failure is immediate and unambiguous

### Likely touch points

- `go/cmd/pcg/local_host.go`
- `go/internal/pcglocal/layout.go`
- `go/internal/pcglocal/owner.go`
- `go/cmd/api/wiring.go`
- `go/cmd/mcp-server/wiring.go`
- `go/cmd/ingester/local_lightweight.go`
- `docs/docs/reference/local-data-root-spec.md`
- `docs/docs/reference/local-host-lifecycle.md`
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`

### Verification

- focused local-host tests for profile/backend resolution
- owner-record round-trip tests including graph metadata
- layout tests proving a stable `graph/` path per workspace
- manual proof that `local_authoritative` fails loudly until sidecar wiring is
  implemented
- opt-in syntax gate against a real NornicDB binary:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBSyntaxVerification -count=1 -v`.
  The 2026-04-22 run failed on PCG's composite node `IS UNIQUE` schema
  syntax and multi-label `CREATE FULLTEXT INDEX` fallback, while passing
  `db.index.fulltext.createNodeIndex(...)` and
  `COLLECT(DISTINCT {map literal})`.
- opt-in workaround gate against the same binary:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBCompatibilityWorkarounds -count=1 -v`.
  The 2026-04-22 run passed composite `IS NODE KEY` and the multi-label
  fulltext procedure form. This supports a future backend-specific schema
  adapter if we choose not to wait for upstream NornicDB parser parity.
- graph schema dialect gate:
  `PCG_NORNICDB_BINARY=/tmp/nornicdb-headless go test ./cmd/pcg -run TestNornicDBSchemaAdapterVerification -count=1 -v`.
  The 2026-04-22 run passed after routing schema bootstrap through the
  backend-specific renderer: Neo4j keeps composite `IS UNIQUE`, while
  NornicDB receives composite `IS NODE KEY`.
- installer gate:
  `go test ./cmd/pcg -run TestInstallNornicDB -count=1`.
  The current branch run passes local-file copy, checksum mismatch rejection,
  JSON output, and managed-binary discovery preference.
- graph log CLI gate:
  `go test ./cmd/pcg -run TestRunGraphLogs -count=1`.
  The current branch run passes workspace-root resolution, log streaming, and
  missing-log guidance without taking ownership of the workspace.
- owner-aware graph stop gate:
  `go test ./cmd/pcg -run TestGraphStop -count=1`.
  The current branch run passes live-owner signaling, stale graph direct stop,
  and lightweight-owner rejection without introducing a second graph owner.
- graph start CLI gate:
  `go test ./cmd/pcg -run TestRunGraphStart -count=1`.
  The current branch run passes foreground exec into `local-host watch` with
  `PCG_QUERY_PROFILE=local_authoritative` and `PCG_GRAPH_BACKEND=nornicdb`.
- graph upgrade CLI gate:
  `go test ./cmd/pcg -run TestRunGraphUpgrade -count=1`.
  The current branch run passes stopped-owner local-file replacement and
  rejects upgrade while a workspace owner or graph backend is still healthy.
- manual local-authoritative lifecycle smoke:
  `PCG_HOME=/tmp/pcg-local-authoritative-smoke ./go/bin/pcg install nornicdb --from /tmp/nornicdb-headless`;
  `./go/bin/pcg graph start --workspace-root <repo>`;
  `./go/bin/pcg graph status --workspace-root <repo>` showed
  `profile=local_authoritative`, `graph_backend=nornicdb`, and
  `graph_running=true`; `./go/bin/pcg graph logs --workspace-root <repo>`
  printed the NornicDB sidecar log; `./go/bin/pcg graph stop --workspace-root <repo>`
  cleanly stopped the owner; final status showed `owner_present=false` and
  `graph_running=false`.
- manual local-authoritative MCP smoke:
  `PCG_HOME=/tmp/pcg-local-authoritative-e2e2 PCG_CANONICAL_WRITE_TIMEOUT=2s ./go/bin/pcg graph start --workspace-root <repo>`;
  `./go/bin/pcg mcp start --workspace-root <repo>`;
  MCP `search_file_content` for `startManagedLocalGraph` returned two Go
  files from `postgres_content_store`; MCP `find_code` returned the
  `startManagedLocalGraph` function with `truth.profile=local_authoritative`
  and `truth.basis=content_index`; `get_index_status` reported degraded graph
  projection after a bounded NornicDB canonical write timeout; `pcg graph stop`
  cleanly stopped the owner and final status showed `owner_present=false`.

---

## Chunk 4: Authoritative Graph Analysis Hardening

### Goal

Ensure the high-value graph-backed code-intelligence surface is solid in full
local stack and production.

### Work

- harden direct caller/callee queries
- harden transitive caller/callee queries
- harden call-chain path queries
- define and implement dead-code policy based on explicit reachability roots
- publish a dead-code reachability spec that covers framework callbacks,
  background workers, SQL entrypoints, and language/framework-specific roots
- ensure reducers materialize the graph truth these queries require

### Required modeling decisions

- what counts as a root for dead-code analysis:
  - `main`
  - HTTP handlers
  - CLI commands
  - framework callbacks
  - tests excluded or not
- how dynamic dispatch and reflection are represented
- how cross-file and cross-repo code calls are admitted

### Conflict-domain reasoning

- reducer acceptance and graph-write phases remain the authoritative bottleneck
- code-call and semantic-entity materialization must not rely on timing or
  watch-loop luck
- completion must be provable from durable state, not inferred from log order

### Likely touch points

- `go/internal/reducer/code_call_*`
- `go/internal/query/code_*`
- `go/internal/storage/neo4j/*`
- `docs/docs/reference/dead-code-reachability-spec.md`
- compose verification scripts for graph-backed queries

### Verification

- positive, negative, and ambiguous truth tests
- full-stack compose validation for callers/callees/path/dead-code
- direct query/API verification against a fresh run
- compose-backed end-to-end validation is mandatory for this chunk

---

## Chunk 5: Backend Conformance Suite

### Goal

Make future graph backend evaluation safe and evidence-based.

### Work

- define backend capability matrix:
  - canonical writes
  - direct graph reads
  - path traversal
  - full-text support
  - dead-code readiness
  - performance envelope
- add a conformance harness that runs the same query corpus against any
  backend adapter under test
- classify backends as:
  - unsupported
  - experimental
  - local-only
  - production-capable
- include deterministic read-shape checks plus write-semantics tests for
  ordering, MERGE/upsert behavior, and transaction visibility

### Important rule

No backend should be described as supported because it "speaks Cypher" alone.

### Likely touch points

- backend test harnesses
- adapter packages
- docs describing backend support status

### Verification

- deterministic conformance runs in CI for supported adapters
- explicit failure reports for missing capability classes

---

## Chunk 6: OCI Collector Plugin Contract

### Goal

Let developers add new collectors without patching the core runtime by hand.

### Work

- define a collector plugin contract at the fact-emission seam
- publish fact-schema versioning and compatibility rules before plugin loading
  work starts
- specify plugin metadata:
  - supported source kinds
  - emitted fact kinds and versions
  - compatibility range
  - packaging metadata
- support OCI artifact distribution for collector plugins
- keep reducers and graph writers unchanged by plugin packaging

### Design rule

Collectors emit versioned facts. They do not write canonical graph truth
directly.

Plugin loading requires an explicit trust model: signing or allowlisting,
provenance checks, and hard failure on incompatible fact-schema versions.

Chunk 6 must not begin until the fact-schema-versioning and plugin-trust-model
specs are frozen.

### Likely touch points

- collector runtime loading
- fact envelope/version negotiation
- `docs/docs/reference/fact-schema-versioning.md`
- `docs/docs/reference/plugin-trust-model.md`
- plugin documentation and packaging tooling

### Verification

- plugin load tests
- fact compatibility tests
- OCI packaging and fetch smoke tests

---

## Observability And Reliability Requirements

Every chunk above must preserve the repo's operating priorities:

1. accuracy
2. performance/concurrency
3. reliability

Required observability themes:

- query truth level must be visible
- local-host process ownership and shutdown must be inspectable
- reducer convergence must be diagnosable from durable state and telemetry
- backend selection must be explicit in logs and spans

Suggested telemetry dimensions:

- `storage_profile`
- `graph_backend`
- `truth_level`
- `workspace_id`
- `repo_scope`

---

## Non-Goals

- replacing Neo4j in production during this implementation
- replacing Postgres in the service profile
- pretending lightweight local mode has full authoritative graph parity
- introducing a new query language
- moving graph or reducer writes into collector plugins
- cross-workspace shared local data roots

---

## Verification Matrix

Minimum verification by work area:

- docs or product-contract changes:
  - `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`
- query contract changes:
  - `cd go && go test ./internal/query ./cmd/api ./cmd/mcp-server -count=1`
  - `cd go && go vet ./internal/query ./cmd/api ./cmd/mcp-server`
- runtime/local-host changes:
  - `cd go && go test ./cmd/pcg ./internal/runtime ./internal/status -count=1`
- facts/reducer/query truth changes:
  - `cd go && go test ./internal/projector ./internal/reducer ./internal/storage/postgres -count=1`
  - compose-backed query verification when graph truth is affected
- Chunk 4 compose end-to-end gate:
  - callers/callees/call-chain/dead-code must pass against a fresh full-stack run
- repo hygiene:
  - `git diff --check`

---

## Implementation Order

The recommended order is:

1. capability contract and truth labels
2. capability-port extraction
3. lightweight local host
4. authoritative graph query hardening
5. backend conformance harness
6. OCI collector plugin seam

This order is deliberate:

- it avoids building local mode on top of unstable query semantics
- it avoids backend experiments before the capability boundaries exist
- it protects production by keeping the authoritative path intact while local
  workflows improve
