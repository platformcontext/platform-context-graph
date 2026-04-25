# PlatformContextGraph

Code-to-cloud context graph for CLI, MCP, and HTTP API workflows. The current
branch is a Go-owned platform runtime:

- **API** serves HTTP reads and admin/query surfaces
- **MCP Server** serves tool-facing read workflows
- **Ingester** owns repo sync, discovery, parsing, and fact emission
- **Reducer** owns queued projection, repair, and shared materialization
- **Bootstrap Index** owns one-shot local or deployment seeding

There is no Python runtime left on the normal platform path. Python remains
only inside fixture corpora used to validate parser behavior.

## Read These First

Before changing runtime, deployment, ingestion, parsing, or observability
behavior, read these pages in this order:

1. `docs/docs/deployment/service-runtimes.md`
2. `docs/docs/reference/local-testing.md`
3. `docs/docs/reference/telemetry/index.md`
4. `docs/docs/architecture.md`

## Runtime Contract

| Runtime | Responsibility | Command | Kubernetes shape |
| --- | --- | --- | --- |
| API | HTTP API, admin/query reads | `pcg api start --host 0.0.0.0 --port 8080` | `Deployment` |
| MCP Server | MCP tool server | `pcg mcp start` | `Deployment` or sidecar |
| Ingester | Repo sync, parse, fact emission | `/usr/local/bin/pcg-ingester` | `StatefulSet` + PVC |
| Reducer | Queue drain, graph projection, repair flows | `/usr/local/bin/pcg-reducer` | `Deployment` |
| Bootstrap Index | One-shot initial indexing | `/usr/local/bin/pcg-bootstrap-index` | job / init step |

Shared backing stores:

- **Neo4j** for the canonical graph
- **Postgres** for facts, queue state, content store, status, and recovery data

## Source Layout

### Go Runtime And Domain Ownership

```text
go/
  cmd/
    api/              # HTTP API binary
    mcp-server/       # MCP server binary
    pcg/              # user-facing CLI
    bootstrap-index/  # one-shot seed/index runtime
    collector-git/    # local proof collector runtime
    ingester/         # deployed ingestion runtime
    projector/        # local proof projector runtime
    reducer/          # deployed reduction/runtime repair ownership
  internal/
    app/              # runtime composition and config
    collector/        # git source ownership, discovery, snapshotting
    content/          # content shaping and persistence
    facts/            # durable fact models and queue contracts
    graph/            # canonical graph schema and write helpers
    mcp/              # MCP transport and tool wiring
    parser/           # native parser registry, adapters, and SCIP support
    pcglocal/         # workspace ownership, data-root layout, flock protocol
    projector/        # fact-stage projection and failure classification
    query/            # HTTP API handlers and OpenAPI surfaces
    recovery/         # replay and repair operations
    reducer/          # cross-domain materialization and shared projection
    relationships/    # Terraform/Helm/Kustomize/Argo relationship extraction
    runtime/          # admin, status, probes, retry policy, lifecycle
    scope/            # repository scope and generation identity
    status/           # pipeline and request lifecycle reporting
    storage/
      neo4j/          # graph adapters
      postgres/       # facts, queue, status, content, recovery, decisions
    telemetry/        # OTEL tracing, metrics, and structured logging
    terraformschema/  # packaged Terraform provider schemas + loader
    truth/            # canonical truth contracts
```

### Python

The historical Python service tree has been deleted from this branch. The only
Python files left in the repository are fixture inputs under `tests/fixtures/`
used to verify parser behavior against real language syntax.

## Local Development

### Full stack

```bash
docker compose up --build
```

This starts:

- Neo4j
- Postgres
- OTEL collector
- Jaeger
- `bootstrap-index`
- `platform-context-graph`
- `ingester`
- `resolution-engine`

Useful checks:

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs ingester | tail -50
docker compose logs resolution-engine | tail -50
curl -s http://localhost:8080/healthz
```

### Direct-command environment

When running commands directly against the local Compose stack:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
```

## Verification Defaults

Use `docs/docs/reference/local-testing.md` as the source of truth. The common
gates are now Go-first:

```bash
cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server ./internal/query ./internal/mcp -count=1
cd go && go test ./internal/parser ./internal/collector/discovery ./internal/content/shape ./internal/collector -count=1
cd go && go test ./internal/terraformschema ./internal/relationships -count=1
cd go && go test ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer ./internal/runtime ./internal/status ./internal/storage/postgres -count=1
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```

### Runtime Repro Hygiene

Before any dogfood, local-authoritative, Compose, or other runtime validation
that executes `go/bin/pcg`, `go/bin/pcg-ingester`, `go/bin/pcg-reducer`,
`go/bin/pcg-api`, or similar local binaries, ALWAYS rebuild the binaries first
so the run reflects the current source tree rather than a stale prior build.
`pcg graph start` discovers `pcg-reducer` and `pcg-ingester` through `PATH`,
so a fresh owner run also needs `go/bin` on `PATH`.

For this repo that usually means:

```bash
cd go
go build -o ./bin/pcg ./cmd/pcg
go build -o ./bin/pcg-api ./cmd/api
go build -o ./bin/pcg-ingester ./cmd/ingester
go build -o ./bin/pcg-reducer ./cmd/reducer
export PATH="$PWD/bin:$PATH"
```

When building or testing NornicDB binaries from the local fork/reference repos
on this machine, ALWAYS use the actual no-local-LLM build tags:

```bash
go test -tags 'noui nolocalllm' ./...
go build -tags 'noui nolocalllm' ...
```

Do not use a plain NornicDB build/test command first and then rediscover the
missing local-LLM dependency the hard way.

## Facts-First Flow

The canonical Git path is:

```text
sync -> discover -> parse -> emit facts -> enqueue work -> reducer -> graph/content projection
```

### Bootstrap Pipeline Phase Ordering (MUST READ before editing any reducer/projector)

The bootstrap-index orchestrator (`go/cmd/bootstrap-index/main.go`) drives a
multi-pass pipeline with strict phase ordering. Editing any domain handler
without understanding this sequence WILL produce bugs that only surface in
full E2E runs.

```text
Phase 1 — Collection + First-Pass Reduction (parallel)
  bootstrap-index collects 896 repos (snapshot → emit facts → enqueue work)
  resolution-engine drains work queue in domain priority order:
    source_local ─────────────────┐
    deployable_unit_correlation ──┤
    workload_identity ────────────┤  All run in first pass.
    workload_materialization ─────┤  NO resolved_relationships exist yet.
    inheritance_materialization ──┤
    code_call_materialization ────┤
    sql_relationship_materialization ┘
    deployment_mapping ───────────── ALL 896 PENDING (runs last or concurrently)

Phase 2 — Backfill (after all projections complete)
  bootstrap-index calls BackfillAllRelationshipEvidence()
    → scans relationship_candidates + fact evidence
    → populates relationship_evidence_facts
    → publishes readiness rows for all 896 generations

Phase 3 — Deployment Mapping Reopen
  bootstrap-index calls ReopenDeploymentMappingWorkItems()
    → reopens 895 succeeded deployment_mapping items
    → resolution-engine processes them with evidence
    → creates resolved_relationships (DEPLOYS_FROM, DEPENDS_ON, etc.)

Phase 4 — ??? Second-pass consumers (GAP as of 2026-04-19)
  workload_materialization needs resolved_relationships to:
    - enrich candidates with DeploymentRepoID
    - resolve environments from deployment repo overlays
    - produce WorkloadInstance nodes
  BUT: no mechanism currently reopens workload_materialization after Phase 3.
  This is the active gap being fixed.
```

**Key rule**: Any domain that consumes `resolved_relationships` MUST have a
re-trigger mechanism after Phase 3 completes. If you add a new domain that
reads resolved_relationships, you MUST also add its reopen step.

Important ownership boundaries:

- `go/internal/collector/` owns Git collection
- `go/internal/parser/` owns parser runtime behavior
- `go/internal/facts/` and `go/internal/storage/postgres/` own durable queue state
- `go/internal/projector/` owns source-local projection stages
- `go/internal/reducer/` owns cross-domain materialization
- `go/internal/query/` owns read/query and admin HTTP surfaces

Do not collapse these boundaries casually. They are the foundation for future
collectors, scaling, and backend work.

## Observability Contract

Every code change that touches runtime behavior MUST include telemetry. This
is not optional. The system runs 878+ repos in production and operators need
to find issues fast, resolve them fast, and tune performance from dashboards
alone.

### What to instrument

| Change type | Required telemetry |
| --- | --- |
| New pipeline stage or worker | OTEL span wrapping the unit of work, duration histogram, success/failure counter |
| New Postgres or Neo4j query | Duration histogram via `InstrumentedDB`, error counter |
| New queue consumer | Claim duration histogram, processing duration histogram, depth gauge |
| New retry/skip path | Counter with reason label, structured log with `failure_class` |
| Memory or resource tuning | Observable gauge reporting configured limit |
| Batch processing | Batch size histogram, batches committed counter |

### How to instrument

- **Metrics** go in `go/internal/telemetry/instruments.go`. All metric names
  use `pcg_dp_` prefix. Register in `NewInstruments()` with explicit bucket
  boundaries for histograms. Add dimension keys to `contract.go` if new.
- **Spans** use `tracer.Start(ctx, telemetry.SpanXxx)`. Add span name
  constants to `contract.go`. Attach `scope_id`, `generation_id`, and
  `collector_kind` attributes when available.
- **Structured logs** use `slog` with `telemetry.ScopeAttrs()` for scope
  context, `telemetry.PhaseAttr()` for pipeline phase, and
  `telemetry.FailureClassAttr()` for error classification.
- **Log keys** are frozen in `contract.go`. Use existing keys before adding
  new ones.

### What NOT to instrument

- Happy-path debug noise (e.g., "processing file X"). Use span events or
  debug-level logs only if the information aids root-cause analysis.
- Per-item metrics where per-batch is sufficient. 295k individual fact
  metrics would overwhelm Prometheus cardinality.
- High-cardinality label values (file paths, fact IDs) as metric attributes.
  These belong in span attributes or structured logs, not counters.

### Key dashboards to support

When adding telemetry, consider these operator questions:

1. **Is it stuck?** — Queue depth gauges, oldest item age, worker pool active
2. **Is it slow?** — Duration histograms per stage, per query, per batch
3. **Is it failing?** — Error counters with `failure_class`, retry counts
4. **Is it using too much memory?** — `pcg_dp_gomemlimit_bytes` gauge,
   `pcg_dp_generation_fact_count` histogram for outlier repos
5. **Did it finish?** — `pcg_dp_facts_committed_total`, projection/reducer
   completed counters, status endpoint health report

### Reference files

- `go/internal/telemetry/contract.go` — frozen dimension keys, span names, log keys
- `go/internal/telemetry/instruments.go` — all metric instruments and registration
- `go/internal/telemetry/providers.go` — OTEL provider bootstrap
- `go/internal/telemetry/logger.go` — structured logger factory
- `docs/docs/reference/telemetry/index.md` — operator-facing telemetry reference

## Deployment Notes

Build once:

```bash
docker build -t platform-context-graph:dev -f Dockerfile .
```

The same image is rendered into:

- API `Deployment`
- MCP `Deployment`
- Ingester `StatefulSet`
- Reducer `Deployment`

The operator contract for those runtimes lives in
`docs/docs/deployment/service-runtimes.md`.

## Documentation Discipline (MANDATORY)

Every code PR that touches user-visible wire contract, CLI flags, environment
variables, runtime profiles, capability ports, collector plugin contracts, or
chunk boundaries MUST include:

1. Update the `## Chunk Status` table (or equivalent progress tracker) in the
   **active ADR or ADRs** governing the work in flight. ADRs live under
   `docs/docs/adrs/`. Each ADR that is in progress should have a
   per-chunk/per-phase status section with commit refs and remaining items.
   If you are not sure which ADR is active, ASK THE USER — do not guess. When
   multiple ADRs are active at once (e.g. a capability-contract ADR and a
   collector ADR), update every active ADR's progress tracker.
2. Update affected user-facing docs when the contract changes:
   - `docs/docs/reference/http-api.md` for HTTP surface changes
   - `docs/docs/reference/cli-reference.md` for CLI flag / profile changes
   - `docs/docs/guides/mcp-guide.md` for MCP tool response shape changes
   - `docs/docs/why-pcg.md` for framework / value-proposition changes
   - `docs/docs/architecture.md` for new capability ports, conformance gates,
     collector seams, or runtime profiles
   - `docs/docs/getting-started/*` when the quickstart/install path changes
3. Any new Go package MUST ship a `doc.go` with a package-level comment that
   names the spec it implements.
4. New extensibility seams (capability ports, collector plugin contracts, DSL
   surfaces) MUST be reflected in `docs/docs/architecture.md` and
   `docs/docs/why-pcg.md` before merge, and in a dedicated reference page
   under `docs/docs/reference/`.

Reviewer rejects PR on doc drift. The `uv run ... mkdocs build --strict` gate
must pass; any reference path added to `docs/mkdocs.yml` must resolve.

Two agents work on this codebase concurrently: Claude Code and Codex. Both
are subject to the same discipline rule. Whichever agent lands a contract
change owns the doc-sync work in that same PR; reviewers reject on drift
regardless of authorship. `CLAUDE.md` and `AGENTS.md` are kept in lockstep —
`AGENTS.md` mirrors `CLAUDE.md` and any edit to one must be mirrored in the
other in the same PR.

## Correlation Truth Gates

Use the `pcg-correlation-truth` skill whenever a change touches workload
admission, deployable-unit correlation, materialization, deployment tracing,
or query truth in `go/internal/reducer`, `go/internal/query`,
`go/internal/graph`, `go/internal/relationships`, or correlation verification
fixtures.

- Do not change correlation logic until you can explain the full path from
  raw evidence → candidate → admission → projection row → graph write →
  query surface.
- Every correlation or materialization change MUST include one positive
  case, one negative case, and one ambiguous case. If any of those classes
  is missing, stop and add it before claiming the design is understood.
- Prove both sides of the contract: what SHOULD materialize and what MUST
  remain provenance-only. Utility repos, controller repos, deployment repos,
  and ambiguous multi-unit repos are mandatory edge-case categories.
- Namespace, folder, or repo-name heuristics MUST NOT invent environment or
  platform truth unless the value matches an explicit environment alias or
  is backed by stronger deployment evidence.
- Reducer completion timing is not valid proof. After the final logic
  patch, run a fresh rebuild/restart path and re-check the graph before
  concluding a miss is timing-related.
- Validation MUST compare fixture intent, reducer graph truth, and
  API/query truth. If any of the three disagree, do not wave it through as
  "close enough"; explain the mismatch or keep digging.
- Required proof for correlation-changing work: focused Go tests for the
  touched packages, a fresh compose correlation run, a direct graph
  inspection of the canonical nodes/edges, and the affected query/API
  surfaces.
- Deployment-story or service-story changes MUST validate repo context,
  service context, and deployment trace together because one surface can
  look healthy while another still lies.

## Graph Backend Axis

PCG supports multiple graph-backend adapters behind the `GraphQuery` and
`GraphWrite` ports. Current adapters:

- `neo4j` — default today, used in Compose and production
- `nornicdb` — pure-Go evaluation candidate; Accepted with conditions per
  `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`

Selection is explicit via `PCG_GRAPH_BACKEND={neo4j,nornicdb}`. Invalid
values are rejected at startup. The axis surfaces in telemetry as
`graph_backend` and optionally in `truth.backend` on responses.

When touching graph-backed code, preserve port boundaries: handlers depend
on `GraphQuery` / `GraphWrite`, never on a concrete adapter type. Backend
dialect translation belongs only in already-documented narrow seams (schema
DDL, canonical-write executor, call-chain/transitive Cypher builders). New
seams require an ADR update before merging.

## Docker Compose macOS Note

If a change affects Docker Compose, read
`docs/docs/deployment/docker-compose.md`. Compose host mounts must use
absolute real directories, not symlinks. On macOS, `/tmp` resolves through a
symlink and is **not** a safe default bind root — use
`/private/tmp/<workspace-id>/` or a repo-local path instead.

## NornicDB Compatibility Workflow (MANDATORY)

When any PCG work hits a NornicDB incompatibility (Cypher parse rejection,
rollback misbehavior, driver shape mismatch, missing procedure, etc.), follow
the workflow documented in
`docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`
§ NornicDB Compatibility Workflow before writing a PCG-side workaround.

Short form:

1. **Check upstream source before guessing.** Local checkouts:
   - `/Users/allen/os-repos/NornicDB/` — upstream reference
   - `/Users/allen/os-repos/NornicDB-pcg-bolt-rollback/` — PCG-maintained
     fork for the grouped-write rollback conformance work

   Use the Grep tool (`rg`) against those paths to confirm what NornicDB
   actually supports or rejects. Do not infer from test failures alone.

2. **Pick the smallest correct fix.**
   - NornicDB supports it → fix the PCG side.
   - NornicDB has a workaround → route PCG through a narrow backend-dialect
     seam (`schemaDialect`, `canonicalExecutorForGraphBackend`,
     `buildCallChainCypher`, etc.). Do not branch handlers on backend brand.
   - NornicDB must be patched → land the fix in
     `NornicDB-pcg-bolt-rollback`, rebuild, and pin the binary through the
     installer manifest or explicit `--from` until upstream absorbs it.

3. **Record the decision** in the NornicDB ADR's adapter evidence row and
   the active Chunk 3.5 / Chunk 4 status row of
   `docs/docs/adrs/2026-04-20-embedded-local-backends-implementation-plan.md`.

Reviewer rejects PR when an `if backend == nornicdb` branch appears outside
an already documented narrow seam.
