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
| `--version`, `-v` | Show the installed PCG version and exit. |
| `--help`, `-h` | Show help and exit. |

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
| `pcg stats [path]` | Show indexing statistics. | No |
| `pcg delete <path>` | Compatibility stub. Prints deletion guidance and exits non-zero. | No |
| `pcg delete --all` | Compatibility stub. Prints deletion guidance and exits non-zero. | No |
| `pcg list` | List indexed repositories. | No |
| `pcg add-package` | Compatibility stub. Prints package-indexing guidance and exits non-zero. | No |
| `pcg watch [path]` | Watch a local path and keep the graph updated. | No |
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
| `pcg analyze calls <function>` | Show what a function calls. | Yes |
| `pcg analyze callers <function>` | Show what calls a function. | Yes |
| `pcg analyze chain <from> <to>` | Show the call chain between two functions. Supports `--depth`. | Yes |
| `pcg analyze deps <module>` | Show import and dependency relationships. | Yes |
| `pcg analyze tree <class>` | Show inheritance hierarchy. | Yes |
| `pcg analyze complexity` | Show relationship-based complexity metrics for one entity. | Yes |
| `pcg analyze dead-code` | Find potentially unused entities, with optional `--repo-id`, `--exclude`, and `--fail-on-found`. | Yes |
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
