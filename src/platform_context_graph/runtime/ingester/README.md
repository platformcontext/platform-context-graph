# Ingester Runtime

The ingester discovers, clones, and indexes repositories for the PCG deployable service. It runs as a StatefulSet in Kubernetes and handles the ongoing sync cycle that keeps the graph up to date.

## Modules

| Module | Responsibility |
| :--- | :--- |
| `config.py` | Runtime configuration and result models |
| `support.py` | Shared runtime helpers and telemetry wiring |
| `git.py` | GitHub and Git checkout/update helpers |
| `bootstrap.py` | Initial clone/sync + indexing flow |
| `sync.py` | Steady-state ingester sync cycle and loop |

## Source Discovery

Repository selection is driven by `PCG_REPOSITORY_RULES_JSON`, which accepts structured exact and regex include rules against normalized `org/repo` identifiers. The legacy `PCG_REPOSITORIES` shorthand is still merged as exact rules for backward compatibility.

Three source modes are supported:

- **`githubOrg`** — org-level discovery with exact/regex filtering
- **`explicit`** — exact repository identifiers only
- **`filesystem`** — an already-materialized local workspace

## CLI Parity

The `pcg workspace` command group uses the same source contract:

- `plan` — preview which repositories match the current config
- `sync` — materialize matching repos into `PCG_REPOS_DIR`
- `index` — index the materialized workspace
- `status` — report workspace config and latest index run
- `watch` — watch the workspace with optional repo rediscovery

Path-first `pcg index <path>` and `pcg watch <path>` remain local convenience wrappers and are not the canonical remote discovery interface.
