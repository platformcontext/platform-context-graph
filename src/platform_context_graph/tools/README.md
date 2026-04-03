# Tools Package

This package now holds the remaining first-class tool surfaces that are still
part of the public package layout.

Canonical ownership for parser, collector, graph, and resolution internals now
lives in the top-level packages below:

- `collectors/` for source-specific collection logic
- `parsers/` for parser-platform code
- `graph/` for graph schema and persistence
- `query/` for read-side search and analysis helpers
- `resolution/` for workload and platform materialization logic

`tools/` intentionally still contains:

- the stable `GraphBuilder` facade
- code-finder and advanced language query surfaces
- cross-repo linker entrypoints
- query-language helper toolkits
- generated artifacts such as `scip_pb2.py`

If you are adding new functionality, prefer the canonical packages above rather
than defaulting to `tools/`.
