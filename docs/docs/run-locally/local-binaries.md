# Local binaries

Use this path when you are developing PCG, testing `pcg graph start`, or running
one workspace with a local owner.

This mode starts embedded Postgres, embedded NornicDB, the ingester, and the
reducer under one workspace owner. It does not start the full HTTP API unless
you run that separately.

## Full local end-to-end

Use this path from a checkout when you want the local owner to manage the graph,
Postgres, ingester, reducer, and MCP helper binaries for one workspace:

```bash
git clone https://github.com/platformcontext/platform-context-graph.git
cd platform-context-graph

./scripts/install-local-binaries.sh
export PATH="$(go env GOPATH)/bin:$PATH"

pcg graph start --workspace-root "$PWD"
```

Leave `pcg graph start` running while you work. It owns the workspace, starts
embedded Postgres, starts embedded NornicDB inside the `pcg` process, launches
`pcg-ingester` and `pcg-reducer` from `PATH`, and prints progress in the
terminal. Stop the owner with `Ctrl-C`, or from another terminal:

```bash
pcg graph stop --workspace-root "$PWD"
```

No local NornicDB install is required for this default path. The script builds
the local owner `pcg` with embedded NornicDB and installs the service binaries
that the owner needs to supervise.

## Install the CLI

For the user-facing CLI, use modern Go install syntax:

```bash
go install -tags nolocalllm github.com/platformcontext/platform-context-graph/go/cmd/pcg@latest
```

Use a pinned version instead of `latest` when you need repeatable installs.
Make sure `$(go env GOPATH)/bin` or `GOBIN` is on `PATH`.

The `nolocalllm` tag is intentional. It links the local NornicDB runtime into
`pcg` without pulling in NornicDB's optional local-LLM pieces, so
`pcg graph start` can run the default local graph without a separate
`nornicdb-headless` install.

This installs only the `pcg` binary. For the full local owner workflow, use the
checkout installer above so `pcg-ingester`, `pcg-reducer`, `pcg-mcp-server`,
and the other helper binaries are present on `PATH`.

## Install the full local binary set

`go install` names binaries after the command directory, so `./cmd/api` becomes
`api`, not `pcg-api`. Local owner mode expects the PCG-prefixed runtime names on
`PATH`, so use the repo installer when you are developing PCG or running
`pcg graph start` from a checkout:

```bash
./scripts/install-local-binaries.sh
```

By default the script installs to `GOBIN`, or to `$(go env GOPATH)/bin` when
`GOBIN` is unset. It installs `pcg`, `pcg-api`, `pcg-mcp-server`,
`pcg-bootstrap-index`, `pcg-ingester`, `pcg-reducer`, and the supporting
runtime helpers.

The script builds only the local owner `pcg` binary with
`PCG_LOCAL_OWNER_BUILD_TAGS=nolocalllm` by default. The service binaries
(`pcg-api`, `pcg-ingester`, `pcg-reducer`, and friends) are plain deployment
style binaries that connect to an external graph endpoint. Set
`PCG_LOCAL_OWNER_BUILD_TAGS=` only when you deliberately want a plain local
owner build for explicit process-mode testing.

`pcg graph start` discovers `pcg-ingester`, `pcg-reducer`, and
`pcg-mcp-server` through `PATH`, so keep that install directory on `PATH` for
the shell where you start PCG.

## NornicDB runtime mode

NornicDB is the default local graph backend. For normal local binary installs,
there is nothing else to install: `pcg graph start` uses the embedded
library-mode runtime in the `pcg` process.

Use an external process only when you are testing a specific NornicDB build:

```bash
PCG_NORNICDB_RUNTIME=process \
PCG_NORNICDB_BINARY=/absolute/path/to/nornicdb-headless \
pcg graph start --workspace-root /path/to/repo
```

`pcg install nornicdb --from <source>` is still available for process-mode
testing and upgrade workflows. Bare `pcg install nornicdb` remains reserved for
future release-backed installs.

## Start a workspace owner

```bash
pcg graph start --workspace-root /path/to/repo
```

This runs in the foreground and prints local progress. Stop it with `Ctrl-C`
when you are done.

## Use MCP with the local owner

If the owner is already running, a stdio MCP process can attach to it:

```bash
pcg mcp start --workspace-root /path/to/repo
```

See [Local MCP](mcp-local.md) for client setup and the difference between local
owner MCP and the Compose MCP service.

## What still needs an API

Read-side CLI commands such as `pcg list`, `pcg stats`, and
`pcg analyze ...` call the HTTP API. Use Docker Compose or run `pcg-api`
separately when you need those API-backed commands.
