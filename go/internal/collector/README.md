# Collector

`collector` owns repository discovery input, snapshot collection, content shaping,
and fact emission setup for PCG indexing runs.

Keep this package focused on turning source repositories into durable facts. It
should not make graph projection decisions or query-time truth decisions; those
belong to reducer, storage, and query packages.

## Dependencies

Internal packages: `internal/collector/discovery`, `internal/content`,
`internal/content/shape`, `internal/facts`, `internal/parser`,
`internal/repositoryidentity`, `internal/scope`, `internal/telemetry`,
`internal/workflow`. Collection consumes parser registration and emits into
the fact contracts in `internal/facts`; it does not depend on graph or query
packages.

## Telemetry

Spans: `telemetry.SpanCollectorObserve`, `telemetry.SpanCollectorStream`,
`telemetry.SpanFactEmit`, `telemetry.SpanScopeAssign`. Phase attributes:
`telemetry.PhaseDiscovery`, `telemetry.PhaseEmission`. Logs use
`telemetry.ScopeAttrs`, `telemetry.PhaseAttr`, and
`telemetry.FailureClassAttr`. Metric instruments live in
`internal/telemetry/instruments.go`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/local-testing.md`
- `docs/docs/reference/cli-reference.md` (`pcg index --discovery-report`)
