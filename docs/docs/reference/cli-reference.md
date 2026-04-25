# CLI Reference

This is the single-page reference for the public `pcg` CLI.

Use this page when you want one place that explains:

- what the CLI can do
- which commands are local-only vs remote-aware
- how remote auth and profiles work
- where to go for deeper topic-specific docs

If you want the shortest path first, start with [CLI K.I.S.S.](cli-kiss.md).

## How the CLI works

`pcg` has two public operating modes:

- Local mode: commands run against your local database, local workspace, and local files.
- Remote mode: selected commands call a deployed PCG HTTP API.

Remote mode is explicit. A command only runs remotely when it supports remote execution and you pass `--service-url` or `--profile`.

Remote mode facts for this release:

- It uses the HTTP API, not MCP.
- It is available for a limited set of query, status, and admin commands.
- Remote `find` and `analyze` commands do not support `--visual`.
- `pcg admin reindex` queues a reindex request for the ingester to execute. The API process does not do the full reindex work inline.
- `pcg admin facts replay` replays dead-lettered facts-first work items back
  to `pending`. It also accepts `failed` rows when older terminal entries are
  still present. It requires at least one selector so operators do not
  accidentally replay the entire terminal set.
- `pcg admin facts dead-letter` moves selected work items into durable terminal state with an operator note.
- `pcg admin facts backfill` creates a durable backfill request for a repository or source run.
- `pcg admin facts replay-events` lists durable replay audit rows for incident review.

Hidden internal runtime commands exist for service containers, but this page documents the public CLI surface.

## Global options

These options apply at the root command level.

| Option | What it does |
| :--- | :--- |
| `--database`, `-db` | Temporarily switch the database backend for one command. |
| `--visual`, `--viz`, `-V` | Ask supported local `find` and `analyze` commands to open graph-style visualization output. |
| `--workspace-root` | Pin the workspace-root directory explicitly. Overrides the resolution order described in [Workspace root and profiles](#workspace-root-and-profiles). Applies to `pcg watch` and `pcg workspace watch`. |
| `--version`, `-v` | Show the installed PCG version and exit. |
| `--help`, `-h` | Show help and exit. |

### Runtime profile

The CLI, MCP server, and HTTP API all accept the same runtime-profile axis via
the `PCG_QUERY_PROFILE` environment variable. Allowed values:
`local_lightweight`, `local_authoritative`, `local_full_stack`, `production`.
Invalid values are rejected at startup. Local-host entrypoints choose their
profile explicitly from command context, while hosted API and MCP runtimes
default to `production` when `PCG_QUERY_PROFILE` is unset.
Truth-level behavior per profile is defined by
[Capability Conformance Spec](capability-conformance-spec.md) and
[Truth Label Protocol](truth-label-protocol.md).

### Graph backend

Separately from profile, PCG selects a graph adapter via
`PCG_GRAPH_BACKEND`. Allowed values: `neo4j` (default), `nornicdb`.
Invalid values are rejected at startup. See
[Graph Backend Installation](graph-backend-installation.md) and
[ADR 2026-04-22](../adrs/2026-04-22-nornicdb-graph-backend-candidate.md)
for the evaluation path.

Today, `local_authoritative` auto-manages NornicDB when a verified NornicDB
binary is available. The laptop default is the headless artifact; the full
binary remains an explicit opt-in. PCG resolves it in this order:

1. `PCG_NORNICDB_BINARY`
2. `${PCG_HOME}/bin/nornicdb-headless` installed by
   `pcg install nornicdb` or `pcg install nornicdb --from <source>`
3. `nornicdb-headless` in `PATH`
4. `nornicdb` in `PATH`

During NornicDB evaluation, local-authoritative canonical graph writes use
bounded phase-group transactions and are still bounded by
`PCG_CANONICAL_WRITE_TIMEOUT` (`15s` by default). The default phase-group size
is `500` statements and can be tuned with
`PCG_NORNICDB_PHASE_GROUP_STATEMENTS=<positive integer>` when repo-scale
dogfood runs need a larger or smaller transaction window. This protects local
MCP/CLI coding workflows from an indefinitely stuck graph write while keeping
content-index-backed code search available even when graph projection is
degraded.

`PCG_NORNICDB_CANONICAL_GROUPED_WRITES=true` is reserved for NornicDB adapter
conformance runs. It enables the same grouped canonical write surface used by
Neo4j so PCG can prove NornicDB rollback, timeout, and no-partial-write
behavior before promotion. The 2026-04-23 safety probe against the rebuilt
linuxdynasty-fork headless binary `/tmp/nornicdb-headless-pcg-rollback`
(`v1.0.42-hotfix`) reports rollback marker count `0` across grouped,
clean-explicit, and failed-explicit rollback surfaces. Keep the switch unset
for normal laptop coding until that fixed binary is release-backed and broader
adapter conformance passes. Manual conformance runs must use a disposable
`PCG_HOME` / workspace data root.

### Graph backend commands

The `local_authoritative` profile runs a graph-backend sidecar alongside the
lightweight host. PCG exposes:

| Command | Purpose |
| :--- | :--- |
| `pcg graph status` | Available now. Report workspace graph-owner metadata, backend, PID, binary path, ports, log path, and current running state when present. |
| `pcg install nornicdb [--from <source>] [--sha256 <hex>] [--force] [--full]` | Available now. Without `--from`, install from the pinned embedded release manifest when the host platform is covered. The current `dev` pin is the rollback-fixed linuxdynasty fork headless tarball for macOS arm64, so headless remains the laptop default. `--full` only succeeds when the manifest includes a matching fixed full published artifact for the current host. With `--from`, verify and copy a NornicDB binary from a local path, tar archive, macOS package, or URL to `${PCG_HOME}/bin/nornicdb-headless`. Remote downloads honor `Ctrl-C` and default to `30s`; override with `PCG_NORNICDB_INSTALL_TIMEOUT=<duration>` when slower links need more time. Signature verification remains future work. |
| `pcg graph logs [--workspace-root <path>]` | Available now. Print the current workspace `graph-nornicdb.log` file if present. |
| `pcg graph stop [--workspace-root <path>]` | Available now. Request the workspace owner to shut down so the managed graph sidecar stops through the normal lifecycle; stale owner graph processes are stopped directly. |
| `pcg graph start [--workspace-root <path>]` | Available now. Foreground shortcut for starting the `local_authoritative` workspace owner, equivalent to `PCG_QUERY_PROFILE=local_authoritative pcg watch .`. During startup and indexing it prints a live progress panel sourced from the shared status store: owner/profile/backend header, collector/projector/reducer flow lanes, and queue pressure. |
| `pcg graph upgrade --from <source> [--sha256 <hex>] [--workspace-root <path>]` | Available now. Replace the managed NornicDB binary from a verified local binary, tar archive, macOS package, or URL; requires the workspace graph to be stopped first. |

Full operator contract: [Graph Backend Operations](graph-backend-operations.md).

## Workspace root and profiles

The lightweight local host treats each workspace as a single-owner filesystem.
A workspace has one data root at `${PCG_HOME}/local/workspaces/<workspace_id>/`.

### Resolution order

When you run `pcg watch .`, `pcg mcp stdio`, or any command that needs a
workspace, PCG picks the workspace root in this order:

1. `--workspace-root <path>` explicit flag
2. Nearest ancestor directory containing `.pcg.yaml`
3. Nearest ancestor directory containing `.git`
4. The current working directory

The resolved path is passed through `realpath`, normalized, and hashed
(SHA-256, first 20 bytes hex) to derive a stable `workspace_id`. Two symlinked
paths that resolve to the same real path converge to the same `workspace_id`.

### PCG_HOME defaults

`PCG_HOME` controls where local host state lives. Override with the
`PCG_HOME` environment variable. Defaults:

| OS | Default |
| --- | --- |
| macOS | `~/Library/Application Support/pcg` |
| Linux | `${XDG_DATA_HOME:-~/.local/share}/pcg` |
| Windows | `%LOCALAPPDATA%\pcg` (ownership + transport deferred) |

### Data-root layout

Each workspace owns one directory tree under `${PCG_HOME}/local/workspaces/<workspace_id>/`:

```text
VERSION            # layout schema version
owner.lock         # flock sentinel for single-owner invariant
owner.json         # current owner metadata (PID, postgres state, optional graph state)
graph/             # optional authoritative graph backend data root
postgres/          # embedded Postgres data directory
logs/              # local-host lifecycle and recovery logs
cache/             # derived local caches (rebuildable)
```

See [Local Data Root Spec](local-data-root-spec.md) and
[Local Host Lifecycle](local-host-lifecycle.md) for the full contract.

## Public command map

### Root commands

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg help` | Show the full root help screen. | No |
| `pcg version` | Print the installed version. | No |
| `pcg doctor` | Run local diagnostics. | No |
| `pcg index [path]` | Index a local path by launching the Go `bootstrap-index` runtime. | No |
| `pcg index-status` | Show the latest checkpointed index status. This is the completeness signal, not process health. | Yes |
| `pcg finalize` | Compatibility stub. Prints the current ingester recovery endpoints and exits non-zero. | No |
| `pcg clean` | Compatibility stub. Prints cleanup guidance and exits non-zero. | No |
| `pcg stats [repo-or-path]` | Show indexing statistics. Existing local paths are normalized to absolute indexed paths; other arguments are treated as repository selectors such as name or repo slug. | No |
| `pcg delete <path>` | Compatibility stub. Prints deletion guidance and exits non-zero. | No |
| `pcg delete --all` | Compatibility stub. Prints deletion guidance and exits non-zero. | No |
| `pcg list` | List indexed repositories. | No |
| `pcg add-package` | Compatibility stub. Prints package-indexing guidance and exits non-zero. | No |
| `pcg watch [path]` | Watch a local path and keep the graph updated. In local-host mode it now prints a live progress panel for indexing and projection instead of a fake percentage bar. | No |
| `pcg unwatch <path>` | Compatibility stub. Prints watcher-lifecycle guidance and exits non-zero. | No |
| `pcg watching` | Compatibility stub. Prints watcher-lifecycle guidance and exits non-zero. | No |
| `pcg query "<query>"` | Run a language-query search against indexed code. | No |
| `pcg start` | Deprecated root alias for `pcg mcp start`. | No |

### Workspace commands

`pcg workspace` is the shared-workspace command group.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg workspace plan` | Queue a workspace reindex plan through the Go admin reindex flow. | No |
| `pcg workspace sync` | Queue a workspace sync through the Go admin reindex flow. | No |
| `pcg workspace index` | Queue a workspace index through the Go admin reindex flow. | No |
| `pcg workspace status` | Show workspace path and latest index summary. | Yes |
| `pcg workspace watch` | Watch the materialized workspace. | No |

### Search commands

`pcg find` is for lookup and discovery in the graph.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg find name <name>` | Exact-name search. | Yes |
| `pcg find pattern <text>` | Substring search. | Yes |
| `pcg find type <type>` | List all nodes of one type. | Yes |
| `pcg find variable <name>` | Find variables by name. | Yes |
| `pcg find content <text>` | Full-text search in source content. | Yes |
| `pcg find decorator <name>` | Find functions with a decorator. | Yes |
| `pcg find argument <name>` | Find functions with a parameter name. | Yes |

### Analysis commands

`pcg analyze` is for graph relationships and code quality signals.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg analyze calls <function>` | Show what a function calls. Supports `--transitive` and `--depth`. | Yes |
| `pcg analyze callers <function>` | Show what calls a function. Supports `--transitive` and `--depth`. | Yes |
| `pcg analyze chain <from> <to>` | Show the call chain between two functions. Supports `--repo`, `--repo-id`, and `--depth`; repo-scoped names are resolved to entity IDs, and if a name is ambiguous the API uses graph reachability as the tie-breaker when exactly one candidate pair is reachable. | Yes |
| `pcg analyze deps <module>` | Show import and dependency relationships. | Yes |
| `pcg analyze tree <class>` | Show inheritance hierarchy. | Yes |
| `pcg analyze complexity` | Show relationship-based complexity metrics for one entity. | Yes |
| `pcg analyze dead-code` | Find derived dead-code candidates after default entrypoint, direct Go Cobra/stdlib-HTTP/controller-runtime signature, Go public-API, test, and generated-code exclusions, with optional `--repo` (ID, name, slug, or path), `--repo-id`, `--limit`, `--exclude`, and `--fail-on-found`. | Yes |
| `pcg analyze overrides <name>` | Find implementations across classes. | Yes |
| `pcg analyze variable <name>` | Show variable definitions and usage. | Yes |

### Admin commands

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg admin reindex` | Queue a remote ingester reindex request. | Yes |
| `pcg admin tuning-report` | Show shared-projection tuning state from the admin API. | Yes |
| `pcg admin facts replay` | Replay failed facts-first work items through the admin API. | Yes |
| `pcg admin facts dead-letter` | Move selected facts-first work items into terminal dead-letter state. | Yes |
| `pcg admin facts skip` | Mark selected facts-first work items as skipped with an operator note. | Yes |
| `pcg admin facts backfill` | Create a durable fact backfill request. | Yes |
| `pcg admin facts list` | List fact work items and durable failure metadata. | Yes |
| `pcg admin facts decisions` | List persisted projection decisions and optional evidence. | Yes |
| `pcg admin facts replay-events` | List durable replay audit rows. | Yes |

### Service, setup, and config commands

| Command | Purpose |
| :--- | :--- |
| `pcg graph status` | Show the current workspace graph-backend owner metadata and runtime state. |
| `pcg graph logs [--workspace-root <path>]` | Print the current workspace graph-backend log file if present. |
| `pcg graph stop [--workspace-root <path>]` | Request graph shutdown through the workspace owner, or stop a stale recorded graph process when the owner is already dead. |
| `pcg graph start [--workspace-root <path>]` | Start the `local_authoritative` workspace owner in the foreground. |
| `pcg graph upgrade --from <source> [--sha256 <hex>] [--workspace-root <path>]` | Replace the managed local graph binary from a binary path, tar archive, macOS package, or URL after the workspace graph is stopped. |
| `pcg install nornicdb [--from <source>] [--sha256 <hex>] [--force]` | Install a verified NornicDB binary into the managed PCG home from the pinned manifest or from a binary path, tar archive, macOS package, or URL. |
| `pcg mcp setup` | Configure IDE and CLI MCP integrations. |
| `pcg mcp start` | Start the MCP server. |
| `pcg mcp tools` | List MCP tools. |
| `pcg api start` | Start the HTTP API server. |
| `pcg serve start` | Start the HTTP API runtime convenience process. Use `pcg mcp start` for MCP. |
| `pcg neo4j setup` | Configure a Neo4j connection. |
| `pcg config show` | Show current config values. |
| `pcg config set <key> <value>` | Set one config value. |
| `pcg config reset` | Reset config to defaults. |
| `pcg config db <backend>` | Quickly switch the default database backend. |

### Ecosystem commands

`pcg ecosystem` is for cross-repository workflows.

| Command | Purpose |
| :--- | :--- |
| `pcg ecosystem index` | Compatibility stub. Prints guidance toward `pcg index`, `pcg workspace index`, or admin reindex flows. |
| `pcg ecosystem status` | Compatibility stub. Prints guidance toward `pcg index-status`, `pcg workspace status`, or admin/status APIs. |
| `pcg ecosystem overview` | Show ecosystem summary statistics. |

### Shortcuts

These are public aliases:

| Shortcut | Expands to |
| :--- | :--- |
| `pcg m` | `pcg mcp setup` |
| `pcg n` | `pcg neo4j setup` |
| `pcg i` | `pcg index` |
| `pcg ls` | `pcg list` |
| `pcg rm` | `pcg delete` compatibility stub |
| `pcg w` | `pcg watch` |

## Remote mode

### Commands that support remote execution

Remote mode is available for:

- `pcg index-status`
- `pcg workspace status`
- `pcg admin reindex`
- `pcg admin tuning-report`
- `pcg admin facts replay`
- `pcg admin facts dead-letter`
- `pcg admin facts skip`
- `pcg admin facts backfill`
- `pcg admin facts list`
- `pcg admin facts decisions`
- `pcg admin facts replay-events`
- `pcg find name`
- `pcg find pattern`
- `pcg find type`
- `pcg find variable`
- `pcg find content`
- `pcg find decorator`
- `pcg find argument`
- `pcg analyze calls`
- `pcg analyze callers`
- `pcg analyze chain`
- `pcg analyze deps`
- `pcg analyze tree`
- `pcg analyze complexity`
- `pcg analyze dead-code`
- `pcg analyze overrides`
- `pcg analyze variable`

### Per-command remote flags

Remote-aware commands use the same flag pattern:

- `--service-url`: remote HTTP base URL
- `--api-key`: bearer token
- `--profile`: named profile for resolving service URL and token

### Remote config keys

You can avoid repeating remote flags by storing config values.

Shared keys:

- `PCG_SERVICE_URL`
- `PCG_API_KEY`
- `PCG_SERVICE_PROFILE`
- `PCG_REMOTE_TIMEOUT_SECONDS`

Profile-specific keys:

- `PCG_SERVICE_URL_<PROFILE>`
- `PCG_API_KEY_<PROFILE>`

Example:

```bash
pcg config set PCG_SERVICE_URL_QA https://pcg.qa.example.test
pcg config set PCG_API_KEY_QA your-token-here
pcg config set PCG_SERVICE_PROFILE QA
```

Then you can run:

```bash
pcg workspace status --profile qa
pcg find name handle_payment --profile qa
pcg admin reindex --profile qa
pcg admin facts replay --profile qa --work-item-id fact-work-123
pcg admin facts list --profile qa --status failed
pcg admin facts decisions --profile qa --repository-id repository:r_payments --source-run-id run-123
```

### Remote mode examples

Check remote workspace status:

```bash
pcg workspace status --service-url https://pcg.qa.example.test --api-key "$PCG_API_KEY"
```

Check checkpointed status:

```bash
pcg index-status --profile qa
```

Treat `pcg index-status` as the latest checkpoint-completeness view. Use the
runtime health/admin/status surfaces for liveness and stage progress instead.

Queue a full workspace rebuild on a deployed ingester:

```bash
pcg admin reindex --profile qa --ingester repository --scope workspace --force
```

Replay one dead-lettered facts-first work item:

```bash
pcg admin facts replay --profile qa --work-item-id fact-work-123
```

Replay failed facts-first work for one repository:

```bash
pcg admin facts replay --profile qa --repository-id repository:r_payments --limit 25
```

Run remote query commands:

```bash
pcg find name handle_payment --profile qa
pcg analyze callers handle_payment --profile qa
pcg analyze complexity --profile qa
```

## Local mode examples

Index the current repository:

```bash
pcg index .
```

Force a clean rebuild of the current repository:

```bash
pcg index . --force
```

List indexed repositories:

```bash
pcg list
```

Watch a local repo for changes:

```bash
pcg watch .
```

Inspect callers before a refactor:

```bash
pcg analyze callers process_payment
```

Inspect indirect callers with an explicit depth bound:

```bash
pcg analyze callers process_payment --transitive --depth 7
```

Search by exact name:

```bash
pcg find name PaymentProcessor
```

Preview shared workspace selection:

```bash
pcg workspace plan
```

Show workspace status:

```bash
pcg workspace status
```

## When to use which path

Use local mode when:

- you are indexing your own checkout
- you want `--visual` output
- you need local-only setup or maintenance commands

Use remote mode when:

- you want to inspect a deployed PCG service
- you want CLI-driven status checks against a hosted workspace
- you want to queue a hosted ingester reindex
- you want to upload a `.pcg` bundle into a deployed service

## Related docs

- [CLI K.I.S.S.](cli-kiss.md)
- [CLI: Indexing & Management](cli-indexing.md)
- [CLI: Analysis & Search](cli-analysis.md)
- [CLI: System](cli-system.md)
- [Configuration](configuration.md)
- [HTTP API](http-api.md)
