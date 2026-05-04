# Cypher Storage

`storage/cypher` owns backend-neutral graph write contracts, canonical writers,
edge helpers, statement metadata, and write instrumentation.

Dialect-specific behavior should stay narrow and explicit. Do not spread
`neo4j` or `nornicdb` conditionals through caller packages when a schema adapter,
writer option, or query builder can own the difference.

## Dependencies

Internal packages: `internal/graph`, `internal/projector`,
`internal/reducer`, `internal/telemetry`. Backend-specific drivers belong
in `internal/storage/neo4j` and the NornicDB adapter; this package owns the
backend-neutral writer contracts.

## Telemetry

Write phase and domain attributes use `telemetry.AttrWritePhase` and
`telemetry.AttrDomain`. Metric instruments are reached through
`telemetry.Instruments` (canonical writes, batch size, write duration in
`internal/telemetry/instruments.go`, all `pcg_dp_canonical_*`).

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`
- `docs/docs/reference/telemetry/index.md`
