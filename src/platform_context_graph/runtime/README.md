# Runtime Package

Background ingestion, bootstrap indexing, and repo maintenance flows live here.

The top-level `platform_context_graph.runtime` package keeps the public runtime
surface stable, while `platform_context_graph.runtime.ingester` contains the
repository-ingester implementation split into focused modules.

Use this package for long-running or container-oriented runtime behavior, not
for public query surfaces.

## Runtime Roles

The deployed service shape is easiest to reason about as two primary roles:

- **API runtime** — serves HTTP and MCP using the shared `query/` layer
- **Repository ingester** — syncs repositories and drives the Git collector and
  graph write pipeline

Internally, the ingester now leans on:

- `collectors/git/` for source discovery and parse execution
- `parsers/` for parser registry and language parsing
- `graph/` for canonical graph persistence
- `resolution/` for workload and platform materialization
