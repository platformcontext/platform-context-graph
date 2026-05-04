# Query

The query package owns HTTP read surfaces, OpenAPI assembly, response
contracts, and graph/content read models.

The public OpenAPI contract is built in Go from `openapi*.go` fragments and is
served at `/api/v0/openapi.json`. Keep handler behavior, OpenAPI fragments, and
`docs/docs/reference/http-api.md` in agreement when changing public routes or
response shapes.

## Dependencies

Internal packages: `internal/buildinfo`, `internal/contentrefs`,
`internal/iacreachability`, `internal/parser`, `internal/recovery`,
`internal/status`, `internal/storage/postgres`, `internal/telemetry`.
Handlers depend on graph and content ports such as `GraphQuery` and the
Postgres content reader, not concrete backend implementations.

## Telemetry

Spans created via `tracer.Start` include
`telemetry.SpanQueryRelationshipEvidence`,
`telemetry.SpanQueryInfraResourceSearch`, and `telemetry.SpanQueryDeadIaC`.
Service attributes use `telemetry.DefaultServiceNamespace` and
`telemetry.EventAttr`. Metric instruments live in
`internal/telemetry/instruments.go`.

## Related docs

- `docs/docs/reference/http-api.md`
- `docs/docs/architecture.md`
- `docs/docs/why-pcg.md`
