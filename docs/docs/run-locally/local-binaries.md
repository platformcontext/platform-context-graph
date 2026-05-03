# Local binaries

Use this path when you are developing PCG, testing `pcg graph start`, or running
one workspace with a local owner.

This mode starts embedded Postgres, a managed NornicDB sidecar, the ingester,
and the reducer. It does not start the full HTTP API unless you run that
separately.

## Install the CLI

For the user-facing CLI, use modern Go install syntax:

```bash
go install github.com/platformcontext/platform-context-graph/go/cmd/pcg@latest
```

Use a pinned version instead of `latest` when you need repeatable installs.
Make sure `$(go env GOPATH)/bin` or `GOBIN` is on `PATH`.

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

`pcg graph start` discovers `pcg-ingester`, `pcg-reducer`, and
`pcg-mcp-server` through `PATH`, so keep that install directory on `PATH` for
the shell where you start PCG.

## Install NornicDB

```bash
pcg install nornicdb
```

NornicDB is the default local graph backend. The local owner uses Postgres for
relational state and NornicDB for graph projection.

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
