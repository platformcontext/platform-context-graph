# mcp-server

## Purpose

`pcg-mcp-server` serves the PCG MCP tool transport over stdio or HTTP. It
mounts the same query layer used by `pcg-api` and dispatches MCP tool
calls through `internal/mcp`. In HTTP mode it composes the shared runtime
admin surface alongside the MCP-specific transport routes.

## Ownership boundary

The MCP server owns MCP transport, session/health endpoints, and the
bridge between MCP tool calls and the mounted Go query surface. It does
not own repository sync, parsing, fact emission, queued projection, or
any writes. Tool definitions live in `internal/mcp/`; query handlers
live in `internal/query/`.

## Entry points

- `main` in `go/cmd/mcp-server/main.go`
- HTTP/query wiring in `go/cmd/mcp-server/wiring.go`
- launched via `pcg mcp start` (see `go/cmd/pcg/service.go`)

## Configuration

- `PCG_MCP_TRANSPORT` — `http` (default) or `stdio`
- `PCG_MCP_ADDR` — HTTP listen address, default `:8080`
- `PCG_POSTGRES_DSN` and the standard Postgres env contract
- `PCG_GRAPH_BACKEND`, `NEO4J_URI`, `NEO4J_USERNAME`,
  `NEO4J_PASSWORD`, `DEFAULT_DATABASE`
- `PCG_QUERY_PROFILE` and `PCG_DISABLE_NEO4J` are read by the shared API
  wiring helpers; API key via `runtime.ResolveAPIKey`

## Telemetry

Uses `telemetry.NewBootstrap("mcp-server")` and `NewProviders`. Logger
scope `mcp-server`/component `mcp-server`. Lifecycle events via
`telemetry.EventAttr` (`runtime.startup.failed`,
`runtime.shutdown.failed`). The shared admin mux exposes `/healthz`,
`/readyz`, `/metrics`, `/admin/status` (see
`internal/runtime/README.md`). MCP-specific endpoints (`/sse`,
`/mcp/message`, `/health`) carry their own auth inside the transport mux.

## Gotchas / invariants

- two transports, two contracts: stdio mode does not start an HTTP
  listener and does not expose the admin surface
- the query API mounted under `/api/` is protected by the query mux; do
  not rely on the MCP transport auth for those routes
- shutdown is signal-driven (`SIGINT`/`SIGTERM`); telemetry providers
  shut down on a fresh background context so traces flushed during
  shutdown are not cut short

## Related docs

- [Service runtimes — MCP Server](../../../docs/docs/deployment/service-runtimes.md#mcp-server)
- [MCP guide](../../../docs/docs/guides/mcp-guide.md)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
