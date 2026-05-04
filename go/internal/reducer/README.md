# Reducer

`reducer` owns cross-domain materialization, queued repair, and shared projection
after source-local facts have been committed.

Reducer changes need careful proof. Track the raw evidence, admitted candidates,
projected rows, graph writes, and query surfaces before changing ordering,
admission, retries, or backend-specific behavior.

## Dependencies

Internal packages: `internal/correlation`, `internal/correlation/engine`,
`internal/correlation/model`, `internal/correlation/rules`,
`internal/facts`, `internal/relationships`, `internal/telemetry`,
`internal/truth`. Graph writes flow through the canonical writers in
`internal/storage/cypher` via the `GraphWrite` port.

## Telemetry

Spans: `telemetry.SpanReducerRun`, `telemetry.SpanReducerIntentEnqueue`,
`telemetry.SpanCrossRepoResolution`, `telemetry.SpanCanonicalWrite`. Phase
attributes: `telemetry.PhaseReduction`, `telemetry.PhaseShared`. Acceptance
and domain attributes: `telemetry.AcceptanceAttrs`, `telemetry.DomainAttrs`,
`telemetry.AttrDomain`, `telemetry.AttrOutcome`, `telemetry.AttrRunner`,
`telemetry.AttrLookupResult`, `telemetry.AttrErrorType`. Logs use
`telemetry.LogKeyDomain`, `telemetry.LogKeyGenerationID`,
`telemetry.LogKeyScopeID`, `telemetry.LogKeyAcceptanceUnitID`,
`telemetry.PhaseAttr`, and `telemetry.FailureClassAttr`. Metric instruments
live in `internal/telemetry/instruments.go`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/telemetry/index.md`
- `docs/docs/reference/local-testing.md`
