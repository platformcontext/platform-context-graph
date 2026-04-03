# System Architecture

PlatformContextGraph (PCG) is a code-to-cloud context graph that connects repositories, infrastructure definitions, runtime topology, and graph-backed query surfaces.

It runs in two modes: locally as a CLI and stdio MCP server, or as a deployed service that exposes HTTP API and MCP while continuously maintaining graph state.

Internally, Phase 1 reorganizes the monorepo around canonical package boundaries
instead of treating `tools/` as the default home for indexing logic.

## High-Level Diagram

```mermaid
graph TD
    Client[CLI / AI Client / HTTP Caller]
    API["PCG API Runtime"]
    Ingester["Repository Ingester"]
    Query[Query Layer]
    Collectors["Collectors (Git today)"]
    Parsers["Parsers Platform"]
    Graph["Graph Persistence + Schema"]
    Resolution["Resolution Helpers"]
    DB[(Graph Database)]
    FS[File System]
    IaC[Terraform / Helm / K8s / Argo CD]
    Content[(Postgres Content Store)]

    Client -- "1. Query (CLI / MCP / HTTP)" --> API
    API -- "2. Resolve request" --> Query
    Query -- "3. Read graph" --> DB
    Query -- "3b. Read cached source / search content" --> Content
    Ingester -- "4. Sync repos and invoke indexing pipeline" --> Collectors
    Collectors -- "5. Discover files and snapshots" --> FS
    Collectors -- "6. Invoke parser registry" --> Parsers
    Parsers -- "7. Parse code and IaC" --> IaC
    Collectors -- "8. Persist parsed snapshots" --> Graph
    Graph -- "9. Store nodes and edges" --> DB
    Graph -- "10. Dual-write file and entity content" --> Content
    Resolution -- "11. Materialize workloads and platform edges" --> DB
```

## Components

| Component | Responsibility |
| :--- | :--- |
| **CLI** | Local command surface for indexing, search, analysis, setup, and runtime management. |
| **MCP Server** | JSON-RPC surface for AI development tools. |
| **HTTP API** | OpenAPI-backed surface for automation and service-to-service use. |
| **Query Layer** | Entity-first query model shared by CLI, MCP, and HTTP. |
| **Collectors** | Source-specific discovery and indexing support. Git is the current canonical collector family. |
| **Parsers** | Parser registry, language parsers, raw-text handling, capability specs, and SCIP parser/runtime helpers. |
| **Graph Layer** | Canonical schema and graph persistence helpers. |
| **Resolution** | Workload and platform materialization after graph writes. |
| **Database Layer** | Graph storage. Neo4j is the canonical backend for deployed services. |
| **Content Store** | PostgreSQL-backed file and entity content cache for deployed API and MCP runtimes. |
| **Ingester Runtime** | Long-running repository ingestion, indexing, retry/backoff, and sync. |
| **Observability** | Shared OTEL instrumentation for API, MCP, and indexing runtime signals. |

## Interfaces

CLI, MCP, and HTTP API are the primary interfaces. All three share the same query layer — there is no separate UI frontend.

The docs site (built with MkDocs) is the public reference surface.

## Data Flow

### Indexing

`pcg index .` or the deployed ingester scans repositories, parses code and IaC,
materializes workloads/platforms, and writes graph data to the database.

When the content store is configured, the same indexing pass also writes file content and entity snippets into Postgres.

In Kubernetes, the repository ingester owns repo sync, retries, discovery,
parsing, and graph writes. The API runtime serves independently.

### Querying

1. A user or agent asks a question.
2. CLI, MCP, or HTTP resolves the request into the shared query layer.
3. The query layer reads the graph and, when needed, the content store.
4. Deployed API and MCP runtimes read content from Postgres and report unavailable content until the ingester has populated it.

## Source Tree

The source package is organized by responsibility under `src/platform_context_graph/`:

- `app/` — service-role entrypoints
- `collectors/` — source-specific collection logic
- `graph/` — canonical graph schema and persistence helpers
- `parsers/` — parser registry, raw-text support, parser capabilities, and SCIP
- `platform/` — shared platform/runtime primitives such as dependency rules, package resolution, and automation-family inference
- `query/` — shared read/query layer
- `resolution/` — workload and platform materialization helpers
- `runtime/` — runtime role management, ingester, and status helpers
- `tools/` — `GraphBuilder` facade plus compatibility shims and remaining legacy helpers

See [Source Layout](reference/source-layout.md) for the full package map.

## Key Technologies

- **Language:** Python 3.10+
- **Parsing:** Tree-sitter plus infrastructure-specific parsers
- **Protocol:** Model Context Protocol (MCP)
- **HTTP:** FastAPI + OpenAPI
- **Database:** Neo4j
- **Content Store:** PostgreSQL
- **Packaging:** Docker, Helm, Argo CD
