# External Integrations

**Analysis Date:** 2026-04-13

## APIs & External Services

**GitHub:**
- What: Git repository cloning, API for repo metadata, GitHub App authentication
- SDK: `requests` library for direct API calls
- Authentication: 
  - Environment var: `GITHUB_APP_ID`, `GITHUB_APP_PRIVATE_KEY`, `GITHUB_INSTALLATION_ID`
  - Implementation: `src/platform_context_graph/runtime/ingester/github_auth.py`
  - Approach: JWT tokens + GitHub App installation token flow
- Retry strategy: Configurable via `PCG_GITHUB_API_RETRY_ATTEMPTS` (default: 5) and `PCG_GITHUB_API_RETRY_DELAY_SECONDS` (default: 5.0)
- Token refresh: `PCG_GITHUB_APP_TOKEN_REFRESH_SECONDS` (default: 60)

## Data Storage

**Databases:**

**Graph Storage (Pluggable):**
- **Neo4j** (Primary)
  - Connection: `NEO4J_URI` (e.g., `bolt://localhost:7687`)
  - Auth: `NEO4J_USERNAME`, `NEO4J_PASSWORD`
  - Database: `DEFAULT_DATABASE` or hardcoded `neo4j`
  - Driver: `neo4j` Python package (5.15.0+)
  - Query language: Cypher
  - Implementation: `src/platform_context_graph/core/database.py`
  - Wrapper: `InstrumentedSession` for query telemetry

- **FalkorDB** (Alternative)
  - Type: In-process graph database (Redis-compatible)
  - Packages: `falkordb` (0.1.0+), `falkordblite` (0.1.0+, non-Windows/Python 3.12+)
  - Implementation: `src/platform_context_graph/core/database_falkordb.py`
  - Remote variant: `src/platform_context_graph/core/database_falkordb_remote.py`

- **KuzuDB** (Alternative)
  - Type: Embedded graph database
  - Implementation: `src/platform_context_graph/core/database_kuzu.py`
  - Capability: Read-only fulltext index strategy

**Relational Storage:**
- **PostgreSQL**
  - Connection: `PCG_CONTENT_STORE_DSN` and `PCG_POSTGRES_DSN`
  - Port (compose): 15432 (internal: 5432)
  - Credentials: User `pcg`, password from env
  - Client: `psycopg` (3.2.0+) with `psycopg_pool` connection pooling
  - Pool config:
    - Min size: 1
    - Max size: max(4, `PCG_COMMIT_WORKERS` + 2)
    - Autocommit: true
  - Usage:
    - Content store: `src/platform_context_graph/content/postgres.py`
    - Facts queue: `src/platform_context_graph/facts/work_queue/postgres.py`
    - Decision storage: `src/platform_context_graph/resolution/decisions/postgres.py`
    - Relationship metadata: `src/platform_context_graph/relationships/postgres.py`
    - Status tracking: `src/platform_context_graph/runtime/status_store_db.py`

**File Storage:**
- Local filesystem only (configured via `PCG_REPOS_DIR`, `PCG_HOME`, `PCG_FILESYSTEM_ROOT`)
- No external blob storage integration (S3, GCS, etc.)

**Caching:**
- No external cache service (Redis, Memcached)
- File hash caching: In-process, controlled by `CACHE_ENABLED` config

## Authentication & Identity

**Auth Provider:**
- Custom implementation with GitHub App OAuth support
- Files:
  - `src/platform_context_graph/runtime/ingester/github_auth.py` - GitHub App token handling
  - `src/platform_context_graph/api/http_auth.py` - HTTP bearer token validation

**HTTP Bearer Auth:**
- Environment variable: `PCG_API_KEY` (optional)
- Auto-generation: Enabled via `PCG_AUTO_GENERATE_API_KEY` (default: false in compose)
- Persistence: `~/.platform-context-graph/.env`
- Implementation: Bearer token in `Authorization` header
- Public paths (no auth required): `/health`, `/api/v0/health`, `/api/v0/openapi.json`, `/api/v0/docs`, `/api/v0/redoc`

**Token Security:**
- JWT cryptography: `PyJWT[crypto]` package for signing/validation
- HMAC validation: `hmac` + `secrets` modules for token generation

## Monitoring & Observability

**Error Tracking:**
- None detected - Errors are logged to structured JSON output

**Tracing & Metrics:**
- **OpenTelemetry (OTEL)**
  - Exporter: OTLP over gRPC (Protocol Buffers)
  - Endpoint: `OTEL_EXPORTER_OTLP_ENDPOINT` (default: http://otel-collector:4317 in compose)
  - Protocol: `OTEL_EXPORTER_OTLP_PROTOCOL` (grpc)
  - Insecure: `OTEL_EXPORTER_OTLP_INSECURE` (true for local)
  - Implementation: `src/platform_context_graph/observability/otel.py`
  - Instrumentation:
    - FastAPI: `OpenTelemetryInstrumentor` auto-instruments HTTP routes
    - Neo4j queries: Custom span wrapper in `InstrumentedSession` (`src/platform_context_graph/core/database.py`)
    - Excluded URLs: `/health`, `/api/v0/health`, `/api/v0/openapi.json`, `/api/v0/docs`, `/api/v0/redoc`

- **Jaeger Backend**
  - Image: `jaegertracing/all-in-one:1.76.0`
  - UI port: 16686
  - OTLP Collection: Enabled via `COLLECTOR_OTLP_ENABLED=true`

- **OTEL Collector**
  - Image: `otel/opentelemetry-collector-contrib:0.143.0`
  - Config: `deploy/observability/otel-collector-config.yaml`
  - Ports:
    - gRPC: 4317
    - HTTP: 4318
    - Prometheus: 9464

**Logs:**
- Structured JSON logging to stdout (production standard)
- Format: Configurable via `PCG_LOG_FORMAT` (json or text)
- Correlation: Automatic trace correlation via context vars
- File sink: Optional via `LOG_FILE_PATH`
- Debug sink: Legacy via `DEBUG_LOG_PATH` (when `DEBUG_LOGS=true`)
- Log levels configurable: `ENABLE_APP_LOGS`, `LIBRARY_LOG_LEVEL`
- Implementation: `src/platform_context_graph/observability/structured_logging.py`

**Metrics Export:**
- Prometheus format (scrape endpoint on port 9464 in docker-compose)
- Exporter: `opentelemetry-exporter-prometheus`

## CI/CD & Deployment

**Hosting:**
- Docker containers (primary)
- Kubernetes (production via Helm)
- Local development: docker-compose

**Container Images:**
- Base: `python:3.12-slim` (multi-stage build)
- Published as: `platform-context-graph:dev` or tagged versions
- Entrypoints: `pcg serve start`, `pcg internal bootstrap-index`, `pcg internal repo-sync-loop`, `pcg internal resolution-engine`

**Kubernetes Deployment:**
- API service: `Deployment` running `pcg serve start --host 0.0.0.0 --port 8080`
- Ingester: `StatefulSet` with PVC running `pcg internal repo-sync-loop`
- Resolution Engine: `Deployment` running `pcg internal resolution-engine`
- Bootstrap: One-shot `Job` running `pcg internal bootstrap-index`
- Helm charts: `deploy/` directory (not fully explored)

**CI Pipeline:**
- Not detected (likely GitHub Actions but not in scope)

## Environment Configuration

**Required environment variables for deployment:**
- `DEFAULT_DATABASE` - Graph backend (neo4j, falkordb, kuzudb)
- `NEO4J_URI`, `NEO4J_USERNAME`, `NEO4J_PASSWORD` - Neo4j connection (if neo4j selected)
- `PCG_CONTENT_STORE_DSN` - PostgreSQL DSN for content
- `PCG_POSTGRES_DSN` - PostgreSQL DSN for facts/queue
- `OTEL_EXPORTER_OTLP_ENDPOINT` - OpenTelemetry collector endpoint (optional)

**Optional for production hardening:**
- `PCG_API_KEY` - HTTP bearer token (if not auto-generating)
- `PCG_ENABLE_PUBLIC_DOCS` - Expose OpenAPI docs (default: true)
- `PCG_LOG_FORMAT` - json for production, text for dev

**Secrets location:**
- Local development: `.env` file (git-ignored)
- Docker Compose: Environment variables passed via compose file
- Kubernetes: Secrets objects referenced in Helm values
- Auto-generation: `~/.platform-context-graph/.env` (local config store)

## Webhooks & Callbacks

**Incoming:**
- None detected - HTTP API is request/response only (no webhook handlers)

**Outgoing:**
- None detected - No callback or webhook emission to external services

## Repository Sources

**Git Sync Modes:**
- File system mode: `PCG_REPO_SOURCE_MODE=filesystem`
- Git clone mode: Direct cloning via `requests` + system `git` command
- GitHub App mode: Token-based authentication for private repos
- Implementation: `src/platform_context_graph/runtime/ingester/git_sync_ops.py`

**Repository Rules:**
- JSON configuration: `PCG_REPOSITORY_RULES_JSON` (array of rule objects)
- .pcgignore support: File-based ignore patterns (gitignore format)

## Content Analysis & AST

**Language Parsing:**
- tree-sitter-based parsing for 20+ languages (Python, JavaScript, TypeScript, Go, Rust, Java, etc.)
- SCIP protocol support for semantic indexing (`src/platform_context_graph/tools/scip_pb2.py`)
- Parser implementations: `src/platform_context_graph/parsers/languages/`
- Parser registry: `src/platform_context_graph/parsers/registry.py`

## MCP (Model Context Protocol)

**MCP Server:**
- Transport: JSON-RPC over stdio (primary) and HTTP (secondary via FastAPI)
- Implementation: `src/platform_context_graph/mcp/server.py`
- Tools exposed: Query tools, code tools, ecosystem tools, indexing tools
- Capabilities: Read-only in API runtime, mutations available in MCP runtime

---

*Integration audit: 2026-04-13*
