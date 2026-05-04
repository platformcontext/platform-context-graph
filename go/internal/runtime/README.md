# Runtime

The runtime package owns shared process wiring: admin muxes, health and status
handlers, datastore configuration, retry policy, memory limits, API key
resolution, and Compose/runtime contract tests.

Changes here usually affect more than one binary. Update local testing docs,
Compose docs, Helm docs, or runtime admin docs when the process contract
changes.

## Dependencies

Internal packages: `internal/buildinfo`, `internal/recovery`,
`internal/status`, `internal/telemetry`. Runtime wires these into shared
admin and probe surfaces; binaries import this package rather than wiring
the same surfaces themselves.

## Telemetry

Bootstraps the OTEL contract for every binary via `telemetry.Bootstrap`
and `telemetry.NewBootstrap`. Uses `telemetry.DefaultServiceNamespace`,
`telemetry.LogKeys`, `telemetry.MetricDimensionKeys`,
`telemetry.SpanNames`, and `telemetry.SkippedRefreshCount` to thread the
shared contract into admin handlers and refresh policy.

## Related docs

- `docs/docs/deployment/service-runtimes.md`
- `docs/docs/deployment/docker-compose.md`
- `docs/docs/reference/local-testing.md`
