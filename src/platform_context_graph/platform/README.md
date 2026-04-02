# Platform Package

This package is the Phase 1 home for cross-cutting platform primitives.

It is intentionally shallow today, but it is no longer empty.

Current canonical ownership includes:

- `dependency_catalog.py` for shared dependency/cache directory exclusion rules

Over time it should continue absorbing shared runtime configuration, database
abstractions, observability glue, and other service-level infrastructure that
should not live inside domain packages.
