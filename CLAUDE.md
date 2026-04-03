# PlatformContextGraph

Code-to-cloud context graph for CLI, MCP, and HTTP API workflows. The current
platform shape is a three-service, facts-first system:

- **API** for HTTP + MCP reads
- **Ingester** for repo sync, parse, and fact emission
- **Resolution Engine** for queued fact projection into the canonical graph

## Read These First

Before changing runtime, deployment, facts-first flow, or observability behavior,
read these pages in this order:

1. `docs/docs/deployment/service-runtimes.md`
2. `docs/docs/reference/local-testing.md`
3. `docs/docs/reference/telemetry/index.md`
4. `docs/docs/architecture.md`

## Runtime Contract

| Runtime | Responsibility | Command | K8s shape |
| --- | --- | --- | --- |
| API | HTTP API, MCP, admin endpoints, canonical graph reads | `pcg serve start --host 0.0.0.0 --port 8080` | `Deployment` |
| Ingester | Repo sync, Git collector, parse, fact emission | `pcg internal repo-sync-loop` | `StatefulSet` + PVC |
| Resolution Engine | Claim fact work items and project graph state | `pcg internal resolution-engine` | `Deployment` |
| Bootstrap Index | One-shot initial sync/index seed | `pcg internal bootstrap-index` | one-shot runtime |

Shared backing stores:

- **Neo4j** for the canonical graph
- **Postgres** for facts, work queue, content store, and runtime metadata

## Source Layout

```text
src/platform_context_graph/
  api/            # FastAPI routers
  app/            # service-role metadata and entrypoint contract
  cli/            # CLI wiring and config catalog
  collectors/     # Git collector implementation
  content/        # Postgres content store
  facts/          # durable facts and fact queue
  graph/          # canonical graph persistence and schema
  indexing/       # coordinator and indexing orchestration
  mcp/            # MCP server and transport
  observability/  # OTEL metrics, traces, and structured logs
  parsers/        # parser registry, languages, SCIP
  query/          # read/query layer
  relationships/  # relationship helpers and linking
  resolution/     # fact projection and workload/platform materialization
  runtime/        # long-running runtime loops
  tools/          # GraphBuilder facade + remaining tool-facing query/linking surfaces
```

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
- `repo-sync`
- `resolution-engine`

Useful checks:

```bash
docker compose ps
docker compose logs bootstrap-index | tail -50
docker compose logs repo-sync | tail -50
docker compose logs resolution-engine | tail -50
curl -s http://localhost:8080/health
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
export PYTHONPATH=src
```

## Verification Defaults

Use `docs/docs/reference/local-testing.md` as the source of truth. These are the
common gates:

```bash
PYTHONPATH=src uv run pytest tests/integration/deployment/test_public_deployment_assets.py -q
PYTHONPATH=src uv run pytest tests/integration/cli/test_cli_commands.py -q
PYTHONPATH=src:. uv run pytest \
  tests/integration/indexing/test_git_facts_end_to_end.py \
  tests/integration/indexing/test_git_facts_projection_parity.py -q
PYTHONPATH=src:. uv run pytest \
  tests/unit/observability/test_fact_resolution_telemetry.py \
  tests/unit/observability/test_fact_runtime_scaling_telemetry.py \
  tests/unit/observability/test_resolution_queue_sampler.py \
  tests/unit/observability/test_facts_first_logging.py -q
python3 scripts/check_python_file_lengths.py --max-lines 500
git diff --check
uv run --with mkdocs --with mkdocs-material --with pymdown-extensions \
  mkdocs build --strict --clean --config-file docs/mkdocs.yml
```

## Facts-First Flow

The canonical Git path is now:

```text
sync -> discover -> parse -> emit facts -> enqueue work -> resolution-engine -> graph/content projection
```

Important ownership boundaries:

- `app/` decides which runtime starts
- `collectors/` owns Git collection
- `facts/` owns durable facts and the work queue
- `resolution/` owns queued projection
- `graph/` owns canonical graph writes
- `query/` owns read surfaces

Do not collapse these boundaries casually. They are the foundation for future
collectors, scaling, and backend work.

## Deployment Notes

Build once:

```bash
docker build -t platform-context-graph:dev -f Dockerfile .
```

Helm renders the same image into:

- API `Deployment`
- Resolution Engine `Deployment`
- Ingester `StatefulSet`

The operator view of that contract lives in
`docs/docs/deployment/service-runtimes.md`.
