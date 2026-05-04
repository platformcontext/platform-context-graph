# api

## Purpose

`pcg-api` serves the PCG HTTP query and admin surface. It reads canonical
graph state from the configured graph backend and reads file/entity
content from Postgres. It mounts the shared runtime admin surface
(`/healthz`, `/readyz`, `/metrics`, `/admin/status`) alongside the API
routes registered by `internal/query`.

## Ownership boundary

The API runtime owns HTTP transport, request authentication, and dispatch
to the query layer. It does not own repo sync (`ingester`,
`collector-git`), parsing, fact emission, queued projection
(`reducer`, `projector`), or any writes.

## Entry points

- `main` in `go/cmd/api/main.go`
- HTTP wiring in `go/cmd/api/wiring.go` (`wireAPI`, `newRouter`,
  `mountRuntimeSurface`)
- launched via `pcg api start` (see `go/cmd/pcg/service.go`)

## Configuration

- `PCG_API_ADDR` — listen address, default `:8080`
- `PCG_POSTGRES_DSN` (or legacy `PCG_CONTENT_STORE_DSN`) — required
- `PCG_QUERY_PROFILE` — default `production`
- `PCG_GRAPH_BACKEND` — `neo4j` or `nornicdb`
- `PCG_DISABLE_NEO4J` — with the local-lightweight profile, skips the
  graph driver
- `DEFAULT_DATABASE` — graph database name, default `neo4j`
- API key resolved via `runtime.ResolveAPIKey`; Bolt details via
  `runtime.OpenNeo4jDriver`

## Telemetry

Uses `telemetry.NewBootstrap` and `telemetry.NewProviders`, with `otelhttp`
middleware named `pcg-api`. Logger scope `api`/component `api`. Lifecycle
events via `telemetry.EventAttr`: `runtime.startup.failed`,
`runtime.server.listening`, `runtime.server.stopped`,
`runtime.postgres.connected`, `runtime.neo4j.connected`. `/metrics` is
exposed through the shared admin mux mounted by `internal/runtime`.

## Gotchas / invariants

- read-only runtime: writes belong to ingester, projector, or reducer
- shutdown waits up to 5s for in-flight requests on `SIGINT`/`SIGTERM`
- `wireAPI` returns a `cleanup` closure that closes Postgres and the
  Neo4j driver; partial wiring failures still free acquired connections
- the API mux is wrapped with `query.AuthMiddleware` before mount

## Related docs

- [Service runtimes — API](../../../docs/docs/deployment/service-runtimes.md#api)
- [HTTP API reference](../../../docs/docs/reference/http-api.md)
- [CLI reference](../../../docs/docs/reference/cli-reference.md)
- [Docker Compose deployment](../../../docs/docs/deployment/docker-compose.md)
