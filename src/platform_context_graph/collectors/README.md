# Collectors Package

Source-specific collection logic lives here.

Collectors are responsible for discovering and extracting source data. They
should not become the dumping ground for graph-wide semantics.

Current canonical collector families:

- `git/` — repository discovery, snapshot handling, `.gitignore`, local
  indexing handoff to the Go bootstrap runtime, and related source indexing
  helpers up to fact emission

Future collectors such as AWS and Confluence should follow the same shape:
source-local collection first, shared graph semantics elsewhere.

Collectors should:

- discover source data
- parse or normalize source-local observations
- emit durable facts

The collector stops at durable facts and work-item creation. Canonical graph
projection is owned by `resolution/`, not by the collector package.

Collectors should not own:

- canonical graph writes
- cross-source matching
- workload/platform graph projection decisions
