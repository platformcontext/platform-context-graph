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
- It is available for a limited set of query, status, bundle-upload, and admin commands.
- Remote `find` and `analyze` commands do not support `--visual`.
- `pcg admin reindex` queues a reindex request for the ingester to execute. The API process does not do the full reindex work inline.
- `pcg admin facts replay` replays dead-lettered facts-first work items back to `pending`. It requires at least one selector so operators do not accidentally replay the entire failed set.
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
| `--version`, `-v` | Show the installed PCG version and exit. |
| `--help`, `-h` | Show help and exit. |

## Public command map

### Root commands

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg help` | Show the full root help screen. | No |
| `pcg version` | Print the installed version. | No |
| `pcg doctor` | Run local diagnostics. | No |
| `pcg index [path]` | Index a local path. | No |
| `pcg index-status [target]` | Show checkpointed index status for a local path or remote run. | Yes |
| `pcg finalize` | Re-run the legacy post-commit bridge against an existing graph for recovery or repair. | No |
| `pcg clean` | Remove orphaned nodes and relationships. | No |
| `pcg stats [path]` | Show indexing statistics. | No |
| `pcg delete <path>` | Delete one indexed repository. | No |
| `pcg delete --all` | Delete every indexed repository. | No |
| `pcg visualize` | Launch the interactive Playground UI. | No |
| `pcg list` | List indexed repositories. | No |
| `pcg add-package` | Add a package dependency node. | No |
| `pcg watch [path]` | Watch a local path and keep the graph updated. | No |
| `pcg unwatch <path>` | Stop watching a path. | No |
| `pcg watching` | List active watchers. | No |
| `pcg query "<cypher>"` | Run a read-only Cypher query. | No |
| `pcg start` | Deprecated root alias for `pcg mcp start`. | No |

### Workspace commands

`pcg workspace` is the shared-workspace command group.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg workspace plan` | Preview which repositories the current workspace config selects. | No |
| `pcg workspace sync` | Materialize the configured workspace without indexing it. | No |
| `pcg workspace index` | Index the configured workspace. | No |
| `pcg workspace status` | Show workspace path and latest index summary. | Yes |
| `pcg workspace watch` | Watch the materialized workspace. | No |

### Search commands

`pcg find` is for lookup and discovery in the graph.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg find name <name>` | Exact-name search. | Yes |
| `pcg find pattern <text>` | Substring search. | Yes |
| `pcg find type <type>` | List all nodes of one type. | No |
| `pcg find variable <name>` | Find variables by name. | No |
| `pcg find content <text>` | Full-text search in source content. | No |
| `pcg find decorator <name>` | Find functions with a decorator. | No |
| `pcg find argument <name>` | Find functions with a parameter name. | No |

### Analysis commands

`pcg analyze` is for graph relationships and code quality signals.

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg analyze calls <function>` | Show what a function calls. | Yes |
| `pcg analyze callers <function>` | Show what calls a function. | Yes |
| `pcg analyze chain <from> <to>` | Show the call chain between two functions. | Yes |
| `pcg analyze deps <module>` | Show import and dependency relationships. | Yes |
| `pcg analyze tree <class>` | Show inheritance hierarchy. | No |
| `pcg analyze complexity` | Show function complexity. | Yes |
| `pcg analyze dead-code` | Find potentially unused functions and classes. | Yes |
| `pcg analyze overrides <name>` | Find implementations across classes. | Yes |
| `pcg analyze variable <name>` | Show variable definitions and usage. | Yes |

### Admin, bundles, and registry

| Command | Purpose | Remote-aware |
| :--- | :--- | :--- |
| `pcg admin reindex` | Queue a remote ingester reindex request. | Yes |
| `pcg admin facts replay` | Replay failed facts-first work items through the admin API. | Yes |
| `pcg admin facts dead-letter` | Move selected facts-first work items into terminal failed state. | Yes |
| `pcg admin facts backfill` | Create a durable fact backfill request. | Yes |
| `pcg admin facts list` | List fact work items and durable failure metadata. | Yes |
| `pcg admin facts decisions` | List persisted projection decisions and optional evidence. | Yes |
| `pcg admin facts replay-events` | List durable replay audit rows. | Yes |
| `pcg bundle export <file>` | Export the current graph to a `.pcg` bundle. | No |
| `pcg bundle import <file>` | Import a `.pcg` bundle into the local database. | No |
| `pcg bundle load <name-or-path>` | Load a local or registry bundle. | No |
| `pcg bundle upload <file>` | Upload a bundle to a remote PCG HTTP service. | Yes |
| `pcg registry list` | List registry bundles. | No |
| `pcg registry search <term>` | Search registry bundles. | No |
| `pcg registry download <name>` | Download a bundle. | No |
| `pcg registry request <name>` | Request bundle generation. | No |

### Service, setup, and config commands

| Command | Purpose |
| :--- | :--- |
| `pcg mcp setup` | Configure IDE and CLI MCP integrations. |
| `pcg mcp start` | Start the MCP server. |
| `pcg mcp tools` | List MCP tools. |
| `pcg api start` | Start the HTTP API server. |
| `pcg serve start` | Start the combined HTTP API and MCP service. |
| `pcg neo4j setup` | Configure a Neo4j connection. |
| `pcg config show` | Show current config values. |
| `pcg config set <key> <value>` | Set one config value. |
| `pcg config reset` | Reset config to defaults. |
| `pcg config db <backend>` | Quickly switch the default database backend. |

### Ecosystem commands

`pcg ecosystem` is for cross-repository workflows.

| Command | Purpose |
| :--- | :--- |
| `pcg ecosystem generation` | Show the active relationship-resolution generation. |
| `pcg ecosystem relationships` | List resolved repository relationships. |
| `pcg ecosystem candidates` | List relationship candidates waiting for review. |
| `pcg ecosystem assert-relationship` | Persist an explicit dependency assertion. |
| `pcg ecosystem reject-relationship` | Persist an explicit dependency rejection. |
| `pcg ecosystem index` | Index all repositories in a manifest. |
| `pcg ecosystem status` | Show per-repository index status. |
| `pcg ecosystem update` | Re-index only stale repositories. |
| `pcg ecosystem link` | Build cross-repository relationships. |
| `pcg ecosystem resolve` | Resolve evidence-backed repository dependencies. |
| `pcg ecosystem overview` | Show ecosystem summary statistics. |
| `pcg ecosystem query` | Run ecosystem-level queries. |

### Shortcuts

These are public aliases:

| Shortcut | Expands to |
| :--- | :--- |
| `pcg m` | `pcg mcp setup` |
| `pcg n` | `pcg neo4j setup` |
| `pcg i` | `pcg index` |
| `pcg ls` | `pcg list` |
| `pcg rm` | `pcg delete` |
| `pcg v` | `pcg visualize` |
| `pcg w` | `pcg watch` |
| `pcg export` | `pcg bundle export` |
| `pcg load` | `pcg bundle load` |

## Remote mode

### Commands that support remote execution

Remote mode is available for:

- `pcg index-status`
- `pcg workspace status`
- `pcg admin reindex`
- `pcg admin facts replay`
- `pcg admin facts dead-letter`
- `pcg admin facts backfill`
- `pcg admin facts list`
- `pcg admin facts decisions`
- `pcg admin facts replay-events`
- `pcg bundle upload`
- `pcg find name`
- `pcg find pattern`
- `pcg analyze calls`
- `pcg analyze callers`
- `pcg analyze chain`
- `pcg analyze deps`
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
pcg config set PCG_SERVICE_URL_QA https://mcp-pcg.qa.ops.bgrp.io
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
pcg workspace status --service-url https://mcp-pcg.qa.ops.bgrp.io --api-key "$PCG_API_KEY"
```

Check checkpointed run status:

```bash
pcg index-status f53c7855e3a12baf --profile qa
```

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

Upload a prebuilt bundle to a deployed service:

```bash
pcg bundle upload vendor-lib.pcg --profile qa --clear
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
