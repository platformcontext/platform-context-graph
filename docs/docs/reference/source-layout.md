# Source Layout

PlatformContextGraph keeps the importable Python package under `src/platform_context_graph/` and organizes it by responsibility instead of by transport-specific duplication.

## Top-Level Package Map

| Package | Responsibility |
| :--- | :--- |
| `app/` | service-role entrypoints and startup wiring |
| `collectors/` | source-specific collection logic such as Git discovery and parse execution |
| `api/` | FastAPI app wiring, dependencies, and HTTP routers |
| `cli/` | Typer entrypoints, command registration, setup flows, and visualization helpers |
| `content/` | content-store providers, content identity helpers, and workspace fallback |
| `core/` | database adapters, watcher/runtime primitives, and low-level support code |
| `domain/` | shared typed entities and response models |
| `facts/` | Phase 1 placeholder boundary for future fact-first models and storage |
| `graph/` | canonical graph schema and persistence helpers |
| `mcp/` | MCP server, transport, tool registry, and handler wiring |
| `observability/` | OTEL bootstrap, runtime state, metrics, and instrumentation helpers |
| `parsers/` | parser registry, raw-text parsing, parser capabilities, language parsers, and SCIP |
| `platform/` | Phase 1 placeholder for shared platform/runtime primitives |
| `query/` | shared read/query services used by CLI, MCP, and HTTP |
| `resolution/` | workload/platform materialization and future shared resolution logic |
| `relationships/` | evidence-backed repo relationship discovery, resolution, persistence, and projection |
| `runtime/` | repo sync, bootstrap indexing, and long-running runtime helpers |
| `tools/` | `GraphBuilder`, compatibility shims, and remaining legacy helpers |
| `utils/` | reusable helper utilities that do not belong to a higher-level subsystem |
| `viz/` | visualization-serving support code |

## CLI Package Layout

The CLI package is split into focused subpackages:

- `cli/commands/`: command registration grouped by workflow
- `cli/helpers/`: reusable helper logic for command implementations
- `cli/registry/`: bundle and registry interactions
- `cli/setup/`: environment setup, IDE wiring, and local runtime installers
- `cli/visualization/`: rendering and output helpers for graph visualizations

`cli/main.py` stays intentionally thin and assembles the Typer application from those packages.

## MCP Package Layout

The MCP package now owns the transport-facing surface instead of scattering
those modules at the package root:

- `mcp/server.py`: MCP server orchestration and tool dispatch
- `mcp/transport.py`: JSON-RPC and stdio transport loops
- `mcp/repo_access.py`: local-checkout handoff and elicitation support
- `mcp/tool_registry.py`: aggregated MCP tool definitions
- `mcp/tools/`: tool manifests grouped by workflow
- `mcp/tools/handlers/`: callable handlers used by the MCP server

## Observability Package Layout

The observability package is a real subsystem rather than a flat file:

- `observability/__init__.py`: public observability API
- `observability/otel.py`: OTEL config, exporters, and context helpers
- `observability/runtime.py`: runtime object and instrumentation hooks
- `observability/metrics.py`: metric-recording helpers
- `observability/state.py`: global runtime lifecycle and test-exporter hooks

This keeps API, MCP, and indexing telemetry consistent.

## Relationships Package Layout

The relationships package owns the post-index repo-correlation pipeline:

- `relationships/models.py`: typed evidence, candidate, assertion, and resolved-relationship models
- `relationships/file_evidence.py`: raw file-based extractors for Terraform, Helm, Kustomize, and ArgoCD
- `relationships/execution.py`: checkout discovery, graph-derived evidence, and Neo4j projection
- `relationships/resolver.py`: evidence dedupe, resolution, and assertion handling
- `relationships/postgres.py`: canonical Postgres store reads and writes
- `relationships/postgres_generation.py`: generation persistence helpers
- `relationships/postgres_support.py`: relationship table schema bootstrap
- `relationships/state.py`: shared store lifecycle
- `relationships/cross_repo_linker.py`: cross-repository infrastructure and deployment linking
- `relationships/cross_repo_linker_support.py`: repository-reference matching helpers

## Content Package Layout

The content package owns portable source retrieval and content-store writes:

- `content/identity.py`: canonical content-entity identifiers
- `content/ingest.py`: dual-write helpers used during indexing
- `content/postgres.py`: PostgreSQL-backed content provider
- `content/workspace.py`: workspace fallback provider for shared server checkouts
- `content/service.py`: provider orchestration and backend preference rules
- `content/state.py`: shared provider lifecycle

## Collectors, Parsers, And Graph Layout

The indexing side now separates source collection, parsing, graph persistence,
and post-index materialization into clearer boundaries:

- `collectors/git/`: repository discovery, `.gitignore`, parse workers, path indexing, finalize helpers, and parse execution
- `parsers/registry.py`: canonical parser registry and worker-friendly parse entrypoints
- `parsers/raw_text.py`: raw-text parser support for searchable non-code artifacts
- `parsers/languages/`: canonical language parser entrypoints that have already moved
- `parsers/capabilities/`: parser capability catalog, models, validation, and packaged specs
- `parsers/scip/`: SCIP indexing helpers
- `graph/schema/`: graph schema creation
- `graph/persistence/`: graph write helpers, batching, content dual-write, commit orchestration, and worker support
- `resolution/workloads/` and `resolution/platforms.py`: workload and platform materialization after graph writes

`tools/graph_builder.py` remains the stable public facade while the underlying
source-of-truth modules move into these canonical packages.

The MCP-facing handlers now live under `mcp/tools/handlers/`, which keeps the
transport boundary separate from parsing and graph-building internals.

## Query Package Layout

The query layer keeps the top-level `query/` boundary, but groups larger
read-side concerns into real subpackages:

- `query/code.py`: code search, relationships, and complexity queries
- `query/compare.py`: environment comparisons
- `query/entity_resolution.py`: canonical entity matching
- `query/infra.py`: infrastructure search and relationship views
- `query/context/`: workload and entity context assembly
- `query/impact/`: dependency-path and change-surface queries
- `query/repositories/`: repository listing, context, and statistics
- `query/content.py`: file/entity content retrieval and indexed content search

## Runtime Package Layout

The runtime boundary stays `runtime/`, with repository-ingester source
acquisition and indexing grouped under its own subpackage:

- `runtime/ingester/config.py`: runtime config and result models
- `runtime/ingester/bootstrap.py`: bootstrap indexing orchestration
- `runtime/ingester/sync.py`: steady-state sync loop
- `runtime/ingester/git.py`: git sync helpers
- `runtime/ingester/support.py`: shared runtime support functions

The ingester increasingly depends on canonical packages rather than `tools/`:

- `collectors/git/` for repo-scoped collection
- `parsers/` for parser-platform code
- `graph/` for canonical graph writes
- `resolution/` for workload/platform materialization

## Platform Package Layout

The `platform/` boundary is still small in Phase 1, but it now owns shared
cross-cutting primitives that do not belong to one collector or one runtime:

- `platform/dependency_catalog.py`: built-in dependency and cache directory exclusion rules

For infrastructure parsing, YAML-family handlers are separated by domain instead of hiding everything in one monolithic file. For example, Kubernetes manifests, Argo CD, Crossplane, Helm, and Kustomize each have their own focused parser module.

## Contributor Standards

- Handwritten Python modules under `src/` must stay at 500 lines or fewer.
- Handwritten Python modules, classes, methods, and functions under `src/` must have Google-style docstrings.
- New package directories should include a short `README.md` so contributors can orient themselves quickly.
- Generated files such as `scip_pb2.py` are explicitly exempt from the handwritten module rule.

Run the repository guards from the root:

```bash
python3 scripts/check_python_file_lengths.py --max-lines 500
python3 scripts/check_python_docstrings.py
```
