# Git Collector

The Git collector owns repository-scoped source acquisition and indexing
support.

It currently contains:

- repository discovery and file filtering
- repo display and `.gitignore` handling
- parse snapshot models and Git-specific fact-emission support
- local indexing handoff points that launch the Go `bootstrap-index` runtime
- remaining Git-specific Python helpers that are still being deleted from the
  branch outside the normal runtime hot path

This package is the canonical home for Git-specific collection behavior used by
the ingester runtime and watcher flows. The legacy Python parse/coordinator
stack has been deleted from this package; normal Git collection now routes
through the Go-owned collector/bootstrap path.
