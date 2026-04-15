# Local Testing Runbook

This is the default verification runbook for engineers, Claude, and Codex on
the Go-owned migration branch.

Use it to answer:

- which commands should I run for this kind of change
- what is the minimum acceptable verification before I call work ready
- how do I run the local full-stack workflow
- how do I validate metrics, traces, and the facts-first pipeline

## Start Here

Treat this file as the verification source of truth.

Before changing runtime or deployment behavior, also read:

- [Service Runtimes](../deployment/service-runtimes.md)
- [Docker Compose](../deployment/docker-compose.md)
- [Telemetry Overview](./telemetry/index.md)

## Default Rule

Run the smallest test set that proves the change, then run the deployment and
docs checks required by the surfaces you touched.

Do not call a change ready without citing the commands you actually ran.

## Common Environment

When running directly against a local Docker Compose stack:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DEFAULT_DATABASE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:15432/platform_context_graph
```

## Compose Host-Path Rules

When you run the stack against host repositories, the bind root must be an
absolute path to a real directory.

- Do not use a symlinked path.
- Do not rely on `~` expansion inside Compose files.
- On macOS, do not use `/tmp` as the host root because Docker Desktop resolves
  it through `/private/tmp`.
- If you copied repositories for Compose testing, copy them into a real
  directory under your home folder and point `PCG_FILESYSTEM_HOST_ROOT` there.

## Quick Verification Matrix

| If you touched | Minimum verification |
| --- | --- |
| Docs, `CLAUDE.md`, `AGENTS.md`, or README files | `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml` |
| CLI/runtime wiring | `cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server -count=1` |
| Status/admin or completeness contract | `cd go && go test ./internal/status ./internal/query ./cmd/api -count=1` and `cd go && go vet ./internal/status ./internal/query ./cmd/api` |
| Parser platform or collector snapshot flow | `cd go && go test ./internal/parser ./internal/collector/discovery ./internal/collector -count=1` |
| Terraform provider-schema evidence or relationship extraction | `cd go && go test ./internal/terraformschema ./internal/relationships ./internal/storage/postgres -count=1` |
| Compose, Helm, or deployable runtime shape | `cd go && go test ./cmd/api ./cmd/bootstrap-index ./cmd/ingester ./cmd/reducer -count=1` and `helm lint deploy/helm/platform-context-graph` |
| Facts-first indexing, queue, or resolution flow | `cd go && go test ./internal/projector ./internal/reducer ./internal/storage/postgres -count=1` |
| Recovery, replay, or repair controls | `cd go && go test ./internal/recovery ./internal/runtime ./internal/status -count=1` |
| Facts-first telemetry or queue scaling | `cd go && go test ./internal/telemetry ./internal/runtime ./internal/projector ./internal/reducer -count=1` |
| Admin replay flow | `cd go && go test ./internal/query ./internal/recovery ./internal/runtime -count=1` |
| Repo hygiene gates | `git diff --check` |

## Go Platform Conversion Gate

Use this gate when validating the Go-owned runtime and collector wiring.

Current ownership:

- `collector-git` owns cycle orchestration, discovery, snapshotting, parsing,
  content shaping, and durable fact commit
- `projector` owns source-local materialization stages and decision recording
- `reducer` owns queued shared projection, platform materialization,
  dependency projection, repair flows, and recovery ownership
- `status` owns scan/reindex request lifecycle
- all runtimes expose `/healthz`, `/readyz`, `/metrics`, and `/admin/status`

Focused Go package gate:

```bash
cd go
go test ./internal/parser ./internal/collector/discovery ./internal/content/shape \
  ./internal/collector ./cmd/collector-git ./cmd/ingester ./cmd/bootstrap-index \
  ./internal/runtime ./internal/app ./internal/telemetry \
  ./internal/storage/neo4j ./internal/storage/postgres \
  ./internal/projector ./internal/reducer ./cmd/reducer -count=1
```

## Terraform Provider-Schema Gate

Use this gate when touching the Terraform provider-schema runtime path or the
schema-driven relationship extractors.

```bash
cd go
go test ./internal/terraformschema ./internal/relationships ./internal/storage/postgres -count=1
```

The canonical packaged schemas live under:

- `go/internal/terraformschema/schemas/*.json.gz`

If this gate fails, fix the Go loader or the Go relationship extraction path.
Do not reintroduce a Python wrapper.

## No-Python Runtime Gate

The runtime-ownership bar is now structural rather than pytest-based.

```bash
rg --files . -g '*.py' | rg -v '^tests/fixtures/'
```

That command should return no runtime Python files. Only fixture data under
`tests/fixtures/` is allowed to remain in Python.

## Bootstrap Projection Concurrency

The `bootstrap-index` one-shot runtime runs projection concurrently using a
goroutine worker pool. Each worker claims a scope-generation work item from
the Postgres projector queue (`SELECT ... FOR UPDATE SKIP LOCKED`) and
independently loads facts, projects, and acks.

### Tuning

| Env var | Default | Description |
| --- | --- | --- |
| `PCG_PROJECTION_WORKERS` | `min(NumCPU, 8)` | Number of concurrent projection goroutines |

Set `PCG_PROJECTION_WORKERS=1` to force sequential processing (useful for
debugging). Values above 8 are supported for machines with high core counts
and fast I/O to Postgres and Neo4j.

### Telemetry signals for tuning

All signals use the `pcg_dp_` prefix and are exported via OTLP and Prometheus.

| Signal | Type | What it tells you |
| --- | --- | --- |
| `pcg_dp_projector_run_duration_seconds` | histogram | Per-item projection wall time. High P95 on a single scope means a large repo is the bottleneck. |
| `pcg_dp_queue_claim_duration_seconds{queue=projector}` | histogram | Time to claim work from Postgres. High values mean lock contention — reduce workers or tune Postgres. |
| `pcg_dp_projections_completed_total{status}` | counter | Success/failure rate. Track `status=failed` for projection errors. |
| `pcg_dp_facts_emitted_total` | counter | Total facts produced by the collector phase. |
| `pcg_dp_facts_committed_total` | counter | Total facts durably committed before projection starts. |
| `pcg_dp_collector_observe_duration_seconds` | histogram | Per-scope collection wall time. Dominated by Git discovery and parsing. |

Structured JSON logs include `worker_id`, `scope_id`, `fact_count`,
`duration_seconds`, and `pipeline_phase` on every projection line:

```json
{"message":"bootstrap projection succeeded","scope_id":"my-repo","worker_id":3,"fact_count":1234,"duration_seconds":2.5,"pipeline_phase":"projection"}
```

Filter by `pipeline_phase=projection` and group by `worker_id` to identify
worker imbalance (one worker stuck on a large repo while others idle).

### Concurrency model

```text
main goroutine
  |
  |-- drainCollector (sequential: sync -> discover -> parse -> commit)
  |
  |-- drainProjector (N goroutine workers)
        |-- worker 0: Claim -> LoadFacts -> Project -> Ack (loop)
        |-- worker 1: Claim -> LoadFacts -> Project -> Ack (loop)
        |-- ...
        |-- worker N-1: Claim -> LoadFacts -> Project -> Ack (loop)
        |
        On first error: cancel shared context -> all workers drain -> errors.Join
```

## Concurrency Tuning Reference

All Go data plane services support environment-driven concurrency tuning.
Set any variable to `1` to force sequential processing (useful for debugging).

| Env Var | Default | Service | What It Controls |
| --- | --- | --- | --- |
| `PCG_PROJECTION_WORKERS` | `min(NumCPU, 8)` | Bootstrap-Index | Concurrent bootstrap projection goroutines |
| `PCG_SNAPSHOT_WORKERS` | `min(NumCPU, 4)` | Ingester / Bootstrap | Concurrent repository snapshot goroutines |
| `PCG_REDUCER_WORKERS` | 1 (sequential) | Reducer | Concurrent reducer intent execution goroutines |
| `PCG_SHARED_PROJECTION_WORKERS` | 1 (sequential) | Reducer | Concurrent shared projection partition goroutines |
| `PCG_SHARED_PROJECTION_PARTITION_COUNT` | 8 | Reducer | Number of partitions per shared projection domain |
| `PCG_SHARED_PROJECTION_BATCH_LIMIT` | 100 | Reducer | Max intents processed per partition batch |
| `PCG_SHARED_PROJECTION_POLL_INTERVAL` | 5s | Reducer | Shared projection cycle poll interval |
| `PCG_SHARED_PROJECTION_LEASE_TTL` | 60s | Reducer | Partition lease time-to-live |

### Collector Concurrency Model

```text
ingester / bootstrap-index
  |
  |-- GitSource.buildCollected (N snapshot workers)
        |-- worker 0: SnapshotRepository -> buildFacts -> collect (loop)
        |-- worker 1: SnapshotRepository -> buildFacts -> collect (loop)
        |-- ...
        |-- worker N-1: SnapshotRepository -> buildFacts -> collect (loop)
        |
        On first error: cancel shared context -> all workers drain
```

### Reducer Concurrency Model

```text
reducer service
  |
  |-- runMainLoop (N reducer workers)
  |     |-- worker 0: Claim -> Execute -> Ack/Fail (loop)
  |     |-- worker 1: Claim -> Execute -> Ack/Fail (loop)
  |     |-- ...
  |
  |-- SharedProjectionRunner (M partition workers)
        |-- worker 0: lease -> batch select -> edge write -> release (loop)
        |-- worker 1: lease -> batch select -> edge write -> release (loop)
        |-- ...
        |
        3 domains × K partitions = 3K work items per cycle
```

## Live Runtime Proof Gates

These scripts allocate their own local ports, start only the required
compose-backed infrastructure, and tear the stack down automatically unless
`PCG_KEEP_COMPOSE_STACK=true` is set.

```bash
./scripts/verify_collector_git_runtime_compose.sh
./scripts/verify_projector_runtime_compose.sh
./scripts/verify_reducer_runtime_compose.sh
./scripts/verify_incremental_refresh_compose.sh
./scripts/verify_relationship_platform_compose.sh
./scripts/verify_admin_refinalize_compose.sh
```

## Local Full Stack

### With fixture ecosystems (default)

Start the full stack with the bundled test fixtures:

```bash
docker compose up --build
```

### With real repositories

To test against real Git repositories from a local directory, set
`PCG_FILESYSTEM_HOST_ROOT` to an absolute path containing one or more
cloned repositories. Each subdirectory with a `.git` folder is
discovered automatically.

```bash
PCG_FILESYSTEM_HOST_ROOT=/path/to/your/repos docker compose up --build
```

Port overrides are available when default ports conflict with other
services (SSH tunnels, other Compose stacks, etc.):

```bash
PCG_FILESYSTEM_HOST_ROOT=/path/to/your/repos \
  PCG_POSTGRES_PORT=25432 \
  NEO4J_HTTP_PORT=27474 \
  NEO4J_BOLT_PORT=27687 \
  PCG_HTTP_PORT=28080 \
  PCG_MCP_PORT=28081 \
  JAEGER_UI_PORT=26686 \
  docker compose up --build
```

**Important notes for real repo testing:**

- The path must be a real directory (not a symlink). On macOS, `/tmp`
  is a symlink to `/private/tmp` which Docker Desktop cannot resolve.
  Use a path under `/Users/` or `/home/`.
- Each repo subdirectory must contain a `.git` directory.
- Large repo sets (10+ repos, thousands of files) require significant
  memory. The bootstrap-index process holds all parsed facts in memory
  during the commit phase. For large repo sets, use a machine with at
  least 16 GB of RAM allocated to Docker.
- Symlinks inside repositories are skipped during the filesystem copy
  phase. This is intentional — symlinks cannot be reliably resolved
  inside the container.

### Services

Both modes bring up:

- Neo4j
- Postgres
- OTEL collector + Jaeger
- `bootstrap-index` (one-shot, seeds the graph and fact store)
- `platform-context-graph` (HTTP API)
- `mcp-server` (MCP tool server)
- `ingester` (ongoing repo sync)
- `resolution-engine` (reducer / shared projection)

### Useful checks

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs ingester | tail -50
docker compose logs resolution-engine | tail -50
```

### Health and pipeline status

Replace `localhost:8080` with the appropriate host and port if using
overrides.

```bash
# Health probes
curl -s http://localhost:8080/healthz
curl -s http://localhost:8080/readyz

# Pipeline summary (scopes, facts, work items, failures)
curl -s http://localhost:8080/admin/status | python3 -m json.tool

# Content store stats
curl -s http://localhost:8080/api/v0/content/stats | python3 -m json.tool

# Query the graph for repositories
curl -s http://localhost:8080/api/v0/repositories | python3 -m json.tool

# Query relationships (if any were built)
curl -s 'http://localhost:8080/api/v0/query' \
  -H 'Content-Type: application/json' \
  -d '{"query": "MATCH (n)-[r]->(m) RETURN labels(n)[0] AS from_type, type(r) AS rel, labels(m)[0] AS to_type, count(*) AS cnt ORDER BY cnt DESC LIMIT 20"}' \
  | python3 -m json.tool
```

## Docs And Hygiene

Before calling a change ready:

```bash
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
git diff --check
```
