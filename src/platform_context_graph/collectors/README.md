# Collectors Package

Source-specific collection logic lives here.

Collectors are responsible for discovering and extracting source data. They
should not become the dumping ground for graph-wide semantics.

Current canonical collector families:

- `git/` — repository discovery, parse execution, finalize, `.gitignore`, and
  related source indexing helpers

Future collectors such as AWS and Confluence should follow the same shape:
source-local collection first, shared graph semantics elsewhere.
