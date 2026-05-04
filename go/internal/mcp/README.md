# MCP

`mcp` owns the Model Context Protocol tool surface for PCG.

MCP tools should return the same truth users get from HTTP query surfaces. If a
tool changes request or response shape, update the MCP guide, HTTP/API docs when
shared, and handler tests together.

## Dependencies

Internal packages: `internal/buildinfo`, `internal/query`. Tool dispatch
calls into the same `http.Handler` chain the API server uses, so request
and response truth stay aligned.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans. Spans and metrics are recorded by `internal/query`
handlers it dispatches into.

## Related docs

- `docs/docs/guides/mcp-guide.md`
- `docs/docs/reference/http-api.md`
- `docs/docs/architecture.md`
