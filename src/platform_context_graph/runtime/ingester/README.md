# Ingester Runtime

This subpackage owns the repository-ingester source sync and indexing lifecycle
for PCG runtime processes.

Module boundaries:

- `config.py` holds runtime configuration and result models.
- `support.py` contains shared runtime helpers and telemetry wiring.
- `git.py` implements GitHub and Git checkout/update helpers.
- `bootstrap.py` runs the initial clone/sync + indexing flow.
- `sync.py` runs the steady-state ingester sync cycle and loop.

Runtime source selection is driven by `PCG_REPOSITORY_RULES_JSON`, which accepts
structured exact and regex include rules. The legacy `PCG_REPOSITORIES`
shorthand is still merged as exact rules for one release.

Public CLI parity works through the `pcg workspace` command group, which uses
the same canonical source contract:

- `plan` previews which repositories match the current source config
- `sync` materializes those repositories into `PCG_REPOS_DIR`
- `index` indexes the materialized workspace
- `status` reports the current workspace configuration and latest checkpointed index run
- `watch` watches the materialized workspace and can rediscover newly added repos on a bounded cadence
- `githubOrg` for org discovery plus exact/regex filtering
- `explicit` for exact repository identifiers only
- `filesystem` for an already-materialized local mono-folder or workspace

Path-first `pcg index <path>` and `pcg watch <path>` remain local filesystem
convenience wrappers. They are not the canonical remote discovery interface.

The top-level `platform_context_graph.runtime` package re-exports the public
entrypoints from here so callers do not need to know the internal layout.
