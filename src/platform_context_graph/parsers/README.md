# Parsers Package

Canonical parser-platform code lives here.

This package owns:

- parser registry construction
- raw-text parser support
- language parser entrypoints
- parser capability metadata and packaged specs
- SCIP indexing helpers

If code answers “how do we parse this source artifact?”, it should prefer
`parsers/` over `tools/`.
