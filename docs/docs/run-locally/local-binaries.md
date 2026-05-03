# Local binaries

Use this path when you are developing PCG, testing `pcg graph start`, or running
one workspace with a local owner.

This mode starts embedded Postgres, a managed NornicDB sidecar, the ingester,
and the reducer. It does not start the full HTTP API unless you run that
separately.

## Build the binaries

From the repository root:

```bash
cd go
go build -o ./bin/pcg ./cmd/pcg
go build -o ./bin/pcg-api ./cmd/api
go build -o ./bin/pcg-mcp-server ./cmd/mcp-server
go build -o ./bin/pcg-bootstrap-index ./cmd/bootstrap-index
go build -o ./bin/pcg-ingester ./cmd/ingester
go build -o ./bin/pcg-reducer ./cmd/reducer
export PATH="$PWD/bin:$PATH"
```

`pcg graph start` discovers `pcg-ingester` and `pcg-reducer` through `PATH`, so
keep `go/bin` on `PATH` for the shell where you start PCG.

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
