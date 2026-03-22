# Query Package

Read-side graph queries and context assembly live here.

This package answers questions about repositories, workloads, entities, infrastructure, and dependency paths without mutating graph state.

## Structure

- `query/code.py` for code search and code-relationship queries.
- `query/compare.py` for environment comparison queries.
- `query/entity_resolution.py` for canonical entity matching.
- `query/infra.py` for infrastructure search and relationship views.
- `query/context/` for workload and entity context assembly.
- `query/impact/` for impact-path and change-surface queries.
- `query/repositories/` for repository listing, context, and statistics.
