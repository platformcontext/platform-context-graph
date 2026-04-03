# Tools Package

This package is now primarily a compatibility boundary.

During Phase 1, canonical ownership moved into clearer top-level packages:

- `collectors/` for source-specific collection logic
- `parsers/` for parser-platform code
- `graph/` for graph schema and persistence
- `query/` for read-side search and analysis helpers
- `resolution/` for workload and platform materialization logic

`tools/` still contains:

- the stable `GraphBuilder` facade
- legacy import shims that preserve existing callers and tests
- a smaller set of not-yet-migrated legacy helpers that Phase 1 has not retired yet

If you are adding new functionality, prefer the canonical packages above rather
than defaulting to `tools/`.
