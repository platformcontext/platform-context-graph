# PlatformContextGraph

Code-to-cloud context graph. Connects source code (30+ languages via tree-sitter), infrastructure-as-code (Terraform, Helm, K8s, ArgoCD, Crossplane, CloudFormation), and derived relationships across repositories. Exposes via CLI, MCP, and HTTP API.

## Architecture

Two services, shared backing stores:

| Service | Role | K8s Shape |
|---|---|---|
| **Ingestor** | Git sync, parse, Neo4j/Postgres writes, finalization | StatefulSet + PVC |
| **API/MCP** | HTTP + MCP read surface, query dispatch | Stateless Deployment |

**Backing stores:** Neo4j (graph), PostgreSQL (content, coverage, relationships, runtime status).

## Source Layout

```
src/platform_context_graph/
  api/            # FastAPI routers
  cli/            # CLI entrypoints, config catalog (all defaults live here)
  content/        # Postgres content store (dual-write + retrieval)
  indexing/        # Coordinator, pipeline, checkpoint, finalization, coverage
  mcp/            # MCP server, transport, tool registry, handlers
  observability/  # OTEL bootstrap, metrics, spans
  query/          # Shared read layer (Cypher queries, story builders)
  relationships/  # Post-index relationship pipeline
  runtime/ingester/ # Sync loop, bootstrap, git ops, workspace lock
  tools/          # Graph builder, parsers, persistence, schema
    languages/    # Per-language tree-sitter parsers
```

## Running Locally

### Full stack (docker-compose)

**IMPORTANT:** Use `docker-compose` (hyphenated), not `docker compose` (space). The project uses Docker Compose v5.

```bash
# Default: indexes tests/fixtures/ecosystems/
docker-compose up --build -d

# With real repos: use absolute paths (not $HOME or ~), Docker can't resolve them
PCG_FILESYSTEM_HOST_ROOT=/Users/allen/pcg-test-workspace docker-compose up --build -d

# Force clean start (wipes Neo4j, Postgres, checkpoints):
docker-compose down -v
PCG_FILESYSTEM_HOST_ROOT=/Users/allen/pcg-test-workspace docker-compose up --build --force-recreate -d

# Check bootstrap progress:
docker-compose logs bootstrap-index 2>&1 | rg "Finalization timings|supported=|entity_counts"

# Check API is up:
curl -s http://localhost:8080/api/v0/health

# Read auto-generated API key:
docker exec platform-context-graph-platform-context-graph-1 cat /data/.platform-context-graph/.env
```

Starts: Neo4j (7474/7687), Postgres (5432), bootstrap-index (one-shot), API (8080), repo-sync (loop).

Port overrides if ports conflict:
```bash
NEO4J_HTTP_PORT=17474 NEO4J_BOLT_PORT=17687 PCG_HTTP_PORT=18080 docker-compose up --build -d
```

**Docker gotcha:** `/tmp` paths don't mount into Docker Desktop on macOS. Use paths under `~/` or `/Users/`. Symlinks to host paths don't work inside containers -- copy repos to a flat directory instead.

### Environment for direct commands

When running tests or scripts outside docker against the docker-compose stack:

```bash
export NEO4J_URI=bolt://localhost:7687
export NEO4J_USERNAME=neo4j
export NEO4J_PASSWORD=change-me
export DATABASE_TYPE=neo4j
export PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph
export PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph
export PYTHONPATH=src
```

Default passwords are `change-me` for both Neo4j and Postgres (from `.env.example` / `docker-compose.yaml`). The API auto-generates a bearer token at startup -- read it with `cat /data/.platform-context-graph/.env` inside the API container.

### Tests

```bash
# Unit tests (no external deps)
PYTHONPATH=src uv run python -m pytest tests/unit/ -q --tb=short

# Parser tests only
PYTHONPATH=src uv run python -m pytest tests/unit/parsers/ -q --tb=line

# Integration tests (needs docker-compose stack)
NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=change-me \
  DATABASE_TYPE=neo4j \
  PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph \
  PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph \
  PYTHONPATH=src uv run python -m pytest tests/integration/ -v --tb=short

# Specific integration suites
# ... tests/integration/test_language_graph.py    -- language graph verification
# ... tests/integration/test_iac_graph.py         -- IaC graph verification
# ... tests/integration/test_full_flow.py         -- cross-repo linking
# ... tests/integration/test_mcp_language_queries.py -- MCP tool routing
```

### Pre-PR checks

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
uv run black --check src tests
PYTHONPATH=src uv run python -m pytest tests/unit/ -q --tb=short
```

### Real-repo integration validation (REQUIRED before any PR touching ingestion)

Changes to the ingestion pipeline, parsers, persistence, or finalization must be validated against a real multi-repo corpus via docker-compose before pushing. Unit tests alone are not sufficient.

**Corpus** (10 repos with cross-repo dependencies, ~2,688 parseable files):

```bash
# Set up workspace with symlinks
mkdir -p /tmp/pcg-test-workspace
ln -sf ~/repos/mobius/iac-eks-argocd           /tmp/pcg-test-workspace/iac-eks-argocd
ln -sf ~/repos/mobius/helm-charts              /tmp/pcg-test-workspace/helm-charts
ln -sf ~/repos/mobius/iac-eks-addons           /tmp/pcg-test-workspace/iac-eks-addons
ln -sf ~/repos/mobius/iac-eks-crossplane       /tmp/pcg-test-workspace/iac-eks-crossplane
ln -sf ~/repos/mobius/iac-eks-observability    /tmp/pcg-test-workspace/iac-eks-observability
ln -sf ~/repos/mobius/crossplane-xrd-irsa-role /tmp/pcg-test-workspace/crossplane-xrd-irsa-role
ln -sf ~/repos/terraform-modules/terraform-module-core-irsa /tmp/pcg-test-workspace/terraform-module-core-irsa
ln -sf ~/repos/services/api-node-boats         /tmp/pcg-test-workspace/api-node-boats
ln -sf ~/repos/services/api-node-bw-home       /tmp/pcg-test-workspace/api-node-bw-home
ln -sf ~/repos/terraform-stacks/terraform-stack-boattrader /tmp/pcg-test-workspace/terraform-stack-boattrader

# Index against running docker-compose stack
NEO4J_URI=bolt://localhost:7687 NEO4J_USERNAME=neo4j NEO4J_PASSWORD=change-me \
  DATABASE_TYPE=neo4j \
  PCG_CONTENT_STORE_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph \
  PCG_POSTGRES_DSN=postgresql://pcg:change-me@localhost:5432/platform_context_graph \
  PYTHONPATH=src uv run pcg index /tmp/pcg-test-workspace
```

**Pass criteria:** All 10 repos in graph, cross-repo relationships resolved, zero Variable nodes (when INDEX_VARIABLES=false), API serves context. See `~/PRD-pcg-ingestion-remediation.md` "What Pass Means for Each Phase" for the full verification script.

### Index a local repo

```bash
PYTHONPATH=src uv run pcg index /path/to/repo
```

### Query Neo4j directly

```bash
PYTHONPATH=src uv run python -c "
import os; os.environ.setdefault('DATABASE_TYPE', 'neo4j')
from platform_context_graph.core import get_database_manager
db = get_database_manager()
driver = db.get_driver()
with driver.session() as s:
    repos = s.run('MATCH (r:Repository) RETURN r.name ORDER BY r.name').data()
    print(f'Total repos: {len(repos)}')
"
```

## Ingestion Pipeline

```
Discovery -> Sync -> Parse -> Snapshot -> Queue -> Commit -> Finalization
```

1. **Discovery** (`tools/graph_builder_indexing_discovery.py`): Walk filesystem, honor .gitignore/.pcgignore, exclude dependency dirs, group by git repo.
2. **Sync** (`runtime/ingester/sync.py`): Git clone/fetch. Lock-protected workspace.
3. **Parse** (`tools/graph_builder_indexing_execution.py`): Tree-sitter for code and HCL/Terraform. YAML dispatch for K8s, ArgoCD, Crossplane, Helm, CloudFormation. Returns `RepositorySnapshot`.
4. **Snapshot** (`indexing/coordinator_storage.py`): Write file data to NDJSON on PVC, clear from memory.
5. **Queue** (`indexing/coordinator_pipeline.py`): Bounded `asyncio.Queue(maxsize=PCG_INDEX_QUEUE_DEPTH)`.
6. **Commit** (`indexing/coordinator_pipeline.py`): Single consumer. Neo4j UNWIND + Postgres dual-write per file batch.
7. **Finalization** (`tools/graph_builder_indexing_execution.py:441`): inheritance, function_calls, infra_links, workloads, relationship_resolution.

**Key config** (defaults in `cli/config_catalog.py`):

| Variable | Default | Purpose |
|---|---|---|
| `PCG_PARSE_WORKERS` | 4 | Concurrent repo parse slots |
| `PCG_INDEX_QUEUE_DEPTH` | 8 | Max queued parsed repos |
| `PCG_REPO_FILE_PARSE_MULTIPROCESS` | false | Process pool for file parsing |
| `PCG_REPO_FILE_PARSE_CONCURRENCY` | 1 | Files parsed concurrently in one repo |
| `PCG_GRAPH_WRITE_TX_FILE_BATCH_SIZE` | 5 | Files per Neo4j transaction |
| `PCG_FILE_BATCH_SIZE` | 50 | Files per commit batch |
| `INDEX_VARIABLES` | true | Variable node creation |
| `PCG_IGNORE_DEPENDENCY_DIRS` | true | Exclude vendor/node_modules/etc |

## API/MCP Surface

Stateless FastAPI reading Neo4j + Postgres.

- `GET /api/v0/health`
- `GET /api/v0/repositories` / `/{id}/context` / `/{id}/story` / `/{id}/stats` / `/{id}/coverage`
- `GET /api/v0/ingesters` / `/{ingester}`
- `POST /api/v0/content/files/read` (repo_id + relative_path)
- `POST /api/v0/code/search` / `/relationships` / `/dead-code` / `/complexity`
- MCP: same tools via `/mcp/message`

Query layer in `query/`. Content store in `content/`. Story builders in `query/story_*.py`.

## Active Work

See `~/PRD-pcg-ingestion-remediation.md` for the current remediation plan. Execution order:
- **Phase 1 (ship now):** Wire `INDEX_VARIABLES=false`, disable global call fallback (precision-over-recall tradeoff -- loses cross-repo name-only CALLS edges), add per-label entity metrics and per-stage finalization timing. Run Tier 1 corpus.
- **Phase 1B (benchmark-gated):** A/B test tx batch size (5/10/25) and multiprocess parsing against Tier 1 numbers. Run Tier 2 stress corpus.
- **Phase 2 (after numbers):** Batch Postgres writes, scope relationship projection, move per-repo finalization stages to post-commit.
- **Phase 3 (evidence-gated):** Concurrent commit (needs lock contention data), scope-filter variables, per-repo call resolution, graph DB prototype.

## Code Style

- Python 3.10+, formatted with `black`
- Max 500 lines per file (checked by `scripts/check_python_file_lengths.py`)
- Docstrings required (checked by `scripts/check_python_docstrings.py`)
- Parser capability specs in `tools/parser_capabilities/specs/*.yaml`
- Generated docs from specs: `PYTHONPATH=src uv run python scripts/generate_language_capability_docs.py`
