# Worker Runtime

This subpackage owns the worker-side source sync and indexing lifecycle for PCG
runtime processes.

Module boundaries:

- `config.py` holds runtime configuration and result models.
- `support.py` contains shared runtime helpers and telemetry wiring.
- `git.py` implements GitHub and Git checkout/update helpers.
- `bootstrap.py` runs the initial clone/sync + indexing flow.
- `sync.py` runs the steady-state worker sync cycle and loop.

Runtime source selection is driven by `PCG_REPOSITORY_RULES_JSON`, which accepts
structured exact and regex include rules. The legacy `PCG_REPOSITORIES`
shorthand is still merged as exact rules for one release.

The top-level `platform_context_graph.runtime` package re-exports the public
entrypoints from here so callers do not need to know the internal layout.
