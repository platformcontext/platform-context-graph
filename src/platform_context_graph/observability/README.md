# Observability Package

OpenTelemetry bootstrap, runtime state, metrics helpers, and the shared structured logging bootstrap live here.

Keep the instrumentation surface centralized so the API, MCP server, and indexer all share the same telemetry conventions.

Current ground rules:

- stdout JSON is the canonical logging output
- OTLP traces are the canonical tracing output
- logs and traces share request, correlation, and span identifiers whenever a span is active
- custom log dimensions belong under `extra_keys`, not as ad hoc top-level fields
- OTEL logs export is not required
- use Jaeger when you need to understand slow indexing or request paths

Service-facing telemetry expectations:

- API and MCP expose request, latency, and error telemetry
- the Git collector exposes repository queue wait, parse, fact emission, commit/projection, and fact-store SQL telemetry
- the Resolution Engine exposes claim latency, idle sleep, active-worker count, work-item completion/failure, fact-load, per-stage projection timings, stage output counts, and stage failure taxonomy
- the facts queue exposes SQL operation telemetry plus backlog depth and oldest-item age by work type and status

Metric labels should stay low-cardinality. Repository ids, run ids, snapshot ids,
and work-item ids belong on spans and structured logs, not on metric labels.

For operator-facing references, see:

- `docs/docs/reference/telemetry/index.md`
- `docs/docs/reference/telemetry/metrics.md`
- `docs/docs/reference/telemetry/traces.md`
- `docs/docs/reference/telemetry/logs.md`
