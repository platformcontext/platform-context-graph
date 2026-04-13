# Source Layout

PlatformContextGraph keeps the importable Python package under `src/platform_context_graph/` and organizes it by responsibility instead of by transport-specific duplication.

For rewrite-era source families, pair this page with the
[Collector Authoring Guide](../guides/collector-authoring.md). The guide covers
service-boundary and traversal rules; this page explains where those decisions
live in the repository today.

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
| `facts/` | typed fact models, Postgres fact storage, fact emission, queue state, and facts-first runtime helpers |
| `graph/` | canonical graph schema and persistence helpers |
| `mcp/` | MCP server, transport, tool registry, and handler wiring |
| `observability/` | OTEL bootstrap, runtime state, metrics, and instrumentation helpers |
| `parsers/` | parser registry, raw-text parsing, parser capabilities, language parsers, and SCIP |
| `platform/` | Shared platform/runtime primitives such as dependency rules, package resolution, and runtime-family inference |
| `query/` | shared read/query services used by CLI, MCP, and HTTP |
| `resolution/` | Resolution Engine orchestration, fact projection, workload/platform materialization, and future shared resolution logic |
| `relationships/` | evidence-backed repo relationship discovery, resolution, persistence, and projection |
| `runtime/` | repo sync, bootstrap indexing, resolution-engine runtime loops, and long-running runtime helpers |
| `tools/` | `GraphBuilder`, code-finder/query helpers, cross-repo linking entrypoints, and generated tool-facing artifacts |
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
- `observability/fact_resolution_metrics.py`: facts-first queue, emission, and Resolution Engine telemetry helpers
- `observability/state.py`: global runtime lifecycle and test-exporter hooks

This keeps API, MCP, and indexing telemetry consistent.

Operator-facing telemetry references live under `reference/telemetry/` with
separate pages for overview, metrics, traces, and logs.

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

## Collectors, Facts, Parsers, And Graph Layout

The indexing side now separates source collection, parsing, graph persistence,
facts, graph persistence, and post-index materialization into clearer
boundaries:

- `collectors/git/`: repository discovery, `.gitignore`, path indexing handoff,
  parse snapshot models, and facts-first Git collection support
- the legacy Python parse/coordinator stack under `collectors/git/` has been
  deleted from the branch; the remaining parser-platform migration work is now
  concentrated in `parsers/**`, `content/ingest.py`, and a smaller set of
  cutover helpers outside the normal collector hot path
- future `collectors/<source>/` families: source-specific adapters for AWS,
  Kubernetes, ETL, and other product domains, but only after the Git cutover
  and parser-platform cutovers finish
- `facts/models/`: typed fact contracts for repository/file/entity observations
- `facts/storage/`: Postgres-backed fact storage
- `facts/work_queue/`: Postgres-backed work item queue used by the Resolution Engine
- `facts/emission/`: source-specific fact emission from parsed snapshots
- `facts/state.py`: shared fact store and queue lifecycle for deployed runtimes
- `indexing/coordinator_facts.py` and `indexing/coordinator_facts_support.py`:
  remaining Git cutover helpers for fact emission, recovery support, and
  facts-first finalization while the last Python runtime ownership is being
  removed
- `parsers/registry.py`: canonical parser registry and worker-friendly parse entrypoints
- `parsers/raw_text.py`: raw-text parser support for searchable non-code artifacts
- `parsers/languages/`: canonical language parser entrypoints and support modules
- `parsers/capabilities/`: parser capability catalog, models, validation, and packaged specs
- `parsers/scip/`: SCIP parser, runtime helpers, and indexing orchestration
- `graph/schema/`: graph schema creation
- `graph/persistence/`: graph write helpers, batching, content dual-write, commit orchestration, worker support, and call/inheritance relationship persistence
- `resolution/orchestration/`: Resolution Engine claim/process loops and the
  shared work-item projection path used by the Go-owned runtime
- `resolution/projection/`: repository/file/entity/relationship/workload/platform projection from stored facts
- `resolution/workloads/` and `resolution/platforms.py`: workload and platform materialization after graph writes

`tools/graph_builder.py` remains the stable public facade while the underlying
source-of-truth modules move into these canonical packages. The legacy Python
post-commit finalization bridge has been deleted from the branch; Python
indexing now requires the facts-first runtime instead of falling back to
ad hoc finalize helpers.

The remaining transition risk is now concentrated in the Python parser matrix
and a smaller set of cutover helpers, not in the deleted post-commit bridge,
the deleted `runtime/ingester/*bridge.py` modules, or the deleted legacy
snapshot/coordinator stack. Non-dependency directory indexing now delegates
from `GraphBuilder` to the Go `bootstrap-index` runtime, and direct single-file
indexing now uses the same Go-owned runtime contract.

The MCP-facing handlers now live under `mcp/tools/handlers/`, which keeps the
transport boundary separate from parsing and graph-building internals.

The important rewrite rule is simple:

- add new collector logic under source-specific collection or facts packages
- add source-local projection under `resolution/`
- add shared cross-domain logic under reducer-owned resolution packages
- do not reintroduce deleted Python finalize-bridge behavior
- do not add new production behavior under the legacy Python parser/indexing
  seam or recreate `runtime/ingester/*bridge.py`

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

The temporary `runtime/ingester/*bridge.py` modules have already been deleted
from the branch. Do not reintroduce them.

The ingester increasingly depends on canonical packages rather than `tools/`:

- `collectors/git/` for repo-scoped collection
- `facts/` for durable source observations and queue state
- `parsers/` for parser-platform code
- `graph/` for canonical graph writes
- `resolution/` for Resolution Engine orchestration and workload/platform materialization

## Go Rewrite Package Layout

The in-progress Go rewrite keeps the same ownership boundaries under `go/` so
the cutover can remove Python runtime ownership instead of recreating it:

- `go/internal/parser/`: parser registry metadata and future native parse
  execution ownership
- `go/internal/collector/discovery/`: parser-aware file discovery, nested repo
  grouping, and repo-local `.gitignore` handling
- `go/internal/content/shape/`: translation from normalized parser payloads
  into the canonical Go content materialization model
- `go/internal/collector/`: collector cycle orchestration, repository
  selection/snapshot ownership, and fact shaping

Current native parser-runtime slice:

- `go/internal/parser/registry.go`: parser-key and extension dispatch
- `go/internal/parser/runtime.go`: native tree-sitter language bootstrap and
  parser creation
- `go/internal/parser/engine.go`: file parse dispatch and prescan fanout
- `go/internal/parser/python_language.go`: first native Python adapter
- `go/internal/parser/go_language.go`: first native Go adapter
- `go/internal/parser/javascript_language.go`: JavaScript/TypeScript/TSX
  adapter slice
- `go/internal/parser/json_language.go`: JSON config adapter slice, including
  package/composer/tsconfig metadata and CloudFormation JSON
- `go/internal/parser/hcl_language.go`: Terraform and Terragrunt adapter slice
- `go/internal/parser/yaml_language.go`, `yaml_semantics.go`, and
  `yaml_helm.go`: infrastructure YAML adapter slice for Kubernetes, Argo CD,
  Crossplane, Kustomize, Helm, and CloudFormation YAML
- `go/internal/parser/dockerfile_language.go`: Dockerfile adapter slice
- `go/internal/parser/sql_language.go`: SQL schema, relationship, migration,
  and partial-recovery adapter slice
- `go/internal/parser/raw_text_engine.go`: raw-text fallback for searchable
  template and config artifacts

These Go packages are the target normal-path runtime ownership. The remaining
Python ownership debt is the local parser/indexing path under
`collectors/git/`, `indexing/`, `parsers/`, and `tools/graph_builder.py`, not
the already-deleted `runtime/ingester/*bridge.py` modules.

The parser cutover is still in progress. SCIP parity, specialized
data-intelligence JSON families, and the remaining long-tail language adapters
are still active cutover work, not finished debt.

Do not start new ingestor families until the Git write-plane cutover, parser
platform cutover, and bridge removal are complete.

## Platform Package Layout

The `platform/` boundary is still small in Phase 1, but it now owns shared
cross-cutting primitives that do not belong to one collector or one runtime:

- `platform/dependency_catalog.py`: built-in dependency and cache directory exclusion rules
- `platform/package_resolver.py`: local package path discovery across Python, npm, Go, Java, Ruby, PHP, C/C++, and Dart ecosystems
- `platform/automation_families.py`: shared automation runtime-family inference used by query enrichers

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
