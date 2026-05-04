# Status

`status` owns the shared reporting shape for pipeline state, backlog, health,
and completeness.

Keep the CLI, HTTP admin, and runtime status views aligned. Operators should not
need a different mental model for each PCG service.

## Dependencies

Internal packages: `internal/buildinfo`. Status JSON shapes are consumed by
`internal/query` (HTTP admin), `internal/runtime` (process wiring), and the
CLI; this package does not import them back.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans. Status output is itself an operator-facing surface and is
the consumer of telemetry counts produced elsewhere.

## Related docs

- `docs/docs/reference/cli-reference.md`
- `docs/docs/reference/http-api.md`
- `docs/docs/architecture.md`
