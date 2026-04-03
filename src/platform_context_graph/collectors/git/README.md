# Git Collector

The Git collector owns repository-scoped source acquisition and indexing
support.

It currently contains:

- repository discovery and file filtering
- repo display and `.gitignore` handling
- parse execution and process-pool parse workers
- indexing orchestration entrypoints
- finalize helpers and parse snapshot models

This package is the canonical home for Git-specific collection behavior used by
the ingester runtime, watcher flows, and indexing coordinator.
