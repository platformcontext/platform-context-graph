# Projector

`projector` owns source-local projection work. It turns committed facts into
canonical graph writes and publishes readiness for reducer-owned shared domains.

Projection code must be idempotent. Queue retries, duplicate claims, and partial
graph writes should converge on the same graph truth instead of creating hidden
second paths.

## Dependencies

Internal packages: `internal/content`, `internal/facts`, `internal/queue`,
`internal/reducer`, `internal/scope`, `internal/telemetry`. Graph writes go
through the canonical writers in `internal/storage/cypher`, not directly
into a backend driver.

## Telemetry

Spans: `telemetry.SpanProjectorRun`, `telemetry.SpanCanonicalProjection`,
`telemetry.SpanCanonicalWrite`, `telemetry.SpanReducerIntentEnqueue`. Phase
attributes: `telemetry.PhaseProjection`. Logs use `telemetry.ScopeAttrs`,
`telemetry.PhaseAttr`, and `telemetry.FailureClassAttr`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/telemetry/index.md`
