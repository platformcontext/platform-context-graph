# Local Testing Runbook

This is the default verification runbook for engineers, Claude, and Codex on
the Go-owned migration branch.

Use it to answer:

- which commands should I run for this kind of change
- what is the minimum acceptable verification before I call work ready
- how do I run the local full-stack workflow
- how do I validate metrics, traces, and the facts-first pipeline

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

## Quick Verification Matrix

| If you touched | Minimum verification |
| --- | --- |
| Docs, `CLAUDE.md`, `AGENTS.md`, or README files | `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml` |
| CLI/runtime wiring | `cd go && go test ./cmd/pcg ./cmd/api ./cmd/mcp-server -count=1` |
| Parser platform or collector snapshot flow | `cd go && go test ./internal/parser ./internal/collector/discovery ./internal/collector -count=1` |
| Terraform provider-schema evidence or relationship extraction | `cd go && go test ./internal/terraformschema ./internal/relationships -count=1` |
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
go test ./internal/terraformschema ./internal/relationships -count=1
```

The canonical packaged schemas live under:

- `go/internal/terraformschema/schemas/*.json.gz`

If this gate fails, fix the Go loader or the Go relationship extraction path.
Do not reintroduce a Python wrapper.

## Python Runtime Regression Gate

The migration bar is now structural rather than pytest-based.

```bash
rg --files . -g '*.py' | rg -v '^tests/fixtures/'
```

That command should return no runtime Python files.

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
