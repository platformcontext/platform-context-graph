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

## Repo-Local Ignore Rules

Repo and workspace indexing honor the target repository's own `.gitignore` files by
default through `PCG_HONOR_GITIGNORE=true`.

- Ignore scope is **repo-local only**. A workspace parent `.gitignore` does not
  leak into sibling repositories.
- Nested `.gitignore` files inside a repo are honored for that repo.
- Ignored files are hard-excluded from repo/workspace ingest: they are not
  parsed, not dual-written to Postgres, and do not create graph state.
- Direct single-file indexing remains an explicit override and can still index a
  targeted file.

Use `.pcgignore` for PCG-specific exclusions that should apply regardless of
Git semantics. Effective exclusion for repo/workspace ingest is the union of
repo-local `.gitignore` and `.pcgignore`.

## Local Stress Tuning

When a repo is slow to ingest, inspect these signals first before changing batch
sizes or database settings:

- repository discovery summary logs:
  `supported=... pcgignore_excluded=... gitignore_excluded=... indexed=...`
- debug-only graph entity batch preparation logs:
  `Prepared graph entity batches for <repo>: Variable=..., Function=...`
- debug-only per-batch write timing logs:
  `Graph write batch entity label=Variable rows=... uid_rows=... name_rows=... duration=...s`

The first benchmark repos for local tuning should remain:

- `~/repos/services/aquasolyachtsales`
- `~/repos/services/api-php-boatwizardwebsolutions`

If `aquasolyachtsales` improves materially after repo-local `.gitignore`
filtering but `api-php-boatwizardwebsolutions` does not, the next tuning target
is the Neo4j write path rather than more discovery filtering.
