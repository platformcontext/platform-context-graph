# Platform Package

This package is the Phase 1 home for cross-cutting platform primitives.

It is intentionally shallow today, but it is no longer empty.

Current canonical ownership includes:

- `dependency_catalog.py` for shared dependency/cache directory exclusion rules
- `package_resolver.py` for cross-ecosystem local package path discovery
- `automation_families.py` for generic automation runtime-family inference

Over time it should continue absorbing shared runtime configuration, database
abstractions, observability glue, and other service-level infrastructure that
should not live inside domain packages.
