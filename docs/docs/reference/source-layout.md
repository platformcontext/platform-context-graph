# Source Layout

PlatformContextGraph is now organized around Go-owned runtime and domain
packages. The historical Python service tree has been deleted.
Only fixture inputs under `tests/fixtures/` still use Python source files, and
those exist solely to exercise parser behavior.

Pair this page with the [Collector Authoring Guide](../guides/collector-authoring.md).
That guide explains boundary rules; this page explains where those boundaries
live in the repository today.

## Top-Level Map

| Path | Responsibility |
| :--- | :--- |
| `go/cmd/` | buildable binaries for API, MCP, CLI, ingester, reducer, bootstrap, and proof runtimes |
| `go/internal/app/` | runtime composition, configuration, and shared service wiring |
| `go/internal/collector/` | Git collection, discovery, snapshotting, and fact shaping |
| `go/internal/content/` | content shaping and content-store persistence |
| `go/internal/facts/` | durable fact models and queue contracts |
| `go/internal/graph/` | canonical graph schema and write helpers |
| `go/internal/mcp/` | MCP transport and tool wiring |
| `go/internal/parser/` | native parser registry, language adapters, and SCIP support |
| `go/internal/projector/` | source-local projection stages and failure classification |
| `go/internal/query/` | HTTP query/admin handlers plus OpenAPI support |
| `go/internal/recovery/` | replay and repair domain logic |
| `go/internal/reducer/` | cross-domain reduction and shared projection ownership |
| `go/internal/relationships/` | infrastructure/deployment evidence extraction and resolution |
| `go/internal/runtime/` | probes, admin/status surfaces, retry policy, lifecycle hooks |
| `go/internal/scope/` | repository scope and generation identities |
| `go/internal/status/` | pipeline lifecycle and request reporting |
| `go/internal/storage/` | Postgres and Neo4j adapters |
| `go/internal/telemetry/` | OTEL tracing, metrics, and structured logging |
| `go/internal/terraformschema/` | packaged Terraform provider schemas and schema loader |
| `go/internal/truth/` | canonical truth contracts |
| `deploy/` | Docker, Helm, compose, and manifest assets |
| `docs/` | operator docs, architecture, workflows, runtime references, and language references |
| `tests/fixtures/` | parser and ecosystem fixture corpora only |

## Runtime Binaries

The service boundary is explicit in `go/cmd/`:

- `api/`: HTTP API binary
- `mcp-server/`: MCP server binary
- `pcg/`: top-level CLI
- `bootstrap-index/`: one-shot indexing seed
- `collector-git/`: local proof collector runtime
- `ingester/`: deployed ingestion runtime
- `projector/`: local proof projector runtime
- `reducer/`: deployed reduction and repair runtime
- `admin-status/`: local status renderer

The normal runtime contract is Go-owned end to end. Do not reintroduce service
logic in a compatibility shell outside these binaries.

## Collector, Parser, And Projection Ownership

The write path is intentionally split:

- `go/internal/collector/` owns Git source acquisition, repository selection,
  discovery, snapshotting, and fact emission
- `go/internal/parser/` owns parser registration, per-file parse execution,
  fixture-matrix language semantics, and SCIP support
- `go/internal/projector/` owns source-local projection stages for entities,
  files, relationships, and workloads
- `go/internal/reducer/` owns cross-domain materialization, shared projection
  intents, platform materialization, dependency projection, and repair flows
- `go/internal/relationships/` owns relationship extraction, including
  Terraform schema-driven evidence backed by the packaged schemas in
  `go/internal/terraformschema/`

This is the normal-path ownership. If a new collector or parser feature is
added, it belongs under these Go packages.

## Query And Admin Ownership

Read and operator surfaces live under:

- `go/internal/query/`: HTTP handlers, request/response contracts, OpenAPI
- `go/internal/mcp/`: MCP transport and tool routing
- `go/internal/runtime/`: `/healthz`, `/readyz`, `/metrics`, `/admin/status`,
  retry policy, runtime lifecycle
- `go/internal/status/`: request lifecycle and indexing completeness reporting

The CLI delegates to the Go binaries and HTTP/query surfaces rather than
embedding a second service stack.

## Storage Ownership

All durable state is accessed through Go storage adapters:

- `go/internal/storage/postgres/`: facts, queues, content store, recovery,
  decisions, status, and lifecycle metadata
- `go/internal/storage/neo4j/`: canonical graph writes and edge helpers
- `go/internal/content/`: content shaping and persistence helpers layered over
  the Postgres store

## Terraform Provider Schemas

Terraform provider schema assets are first-class runtime inputs, not leftover
artifacts:

- packaged assets live in `go/internal/terraformschema/schemas/*.json.gz`
- the loader and classification logic live in `go/internal/terraformschema/`
- runtime relationship extraction uses those assets through
  `go/internal/relationships/`

If provider schemas move or change format, update both the runtime code and the
operator docs so the dependency remains explicit.

## What Is Gone

The following ownership has been removed:

- Python runtime entrypoints
- Python API/MCP/CLI service code
- Python collector and parser runtime bridges
- Python finalization and repair bridges
- Python packaged Terraform runtime ownership

If an older note or plan disagrees with this page, treat this page and the
published runtime/workflow docs as the current architecture.
