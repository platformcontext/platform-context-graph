# Postgres Storage

`storage/postgres` owns PCG relational persistence: facts, queue state, content,
status, recovery data, and workflow coordination tables.

Postgres changes must be retry-safe and observable. Think through transaction
scope, lease timing, idempotency, and partial failure before changing queue or
status writes.

## Dependencies

Internal packages: `internal/content`, `internal/contentrefs`,
`internal/facts`, `internal/iacreachability`, `internal/projector`,
`internal/recovery`, `internal/reducer`, `internal/relationships`,
`internal/runtime`, `internal/scope`, `internal/status`,
`internal/telemetry`, `internal/workflow`. Callers depend on this package
through typed queue, content, and recovery helpers rather than raw SQL.

## Telemetry

Spans created via `tracer.Start` include
`telemetry.SpanIaCReachabilityMaterialization`. Phase attributes:
`telemetry.PhaseEmission`, `telemetry.PhaseProjection`. Outcome and scope
attributes: `telemetry.AttrOutcome`, `telemetry.ScopeAttrs`. Refresh and
queue observers: `telemetry.QueueObserver`,
`telemetry.RecordSkippedRefresh`, `telemetry.LogKeyRefreshSkipped`. Logs
use `telemetry.LogKeyGenerationID`, `telemetry.LogKeyScopeID`,
`telemetry.LogKeyScopeKind`, `telemetry.LogKeyCollectorKind`,
`telemetry.LogKeySourceSystem`, and `telemetry.PhaseAttr`. The package
wraps the driver in `InstrumentedDB`; metric instruments live in
`internal/telemetry/instruments.go`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/local-testing.md`
- `docs/docs/deployment/docker-compose.md`
