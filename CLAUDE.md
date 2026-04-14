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

## Facts-First Flow

The canonical Git path is:

```text
sync -> discover -> parse -> emit facts -> enqueue work -> reducer -> graph/content projection
```

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
