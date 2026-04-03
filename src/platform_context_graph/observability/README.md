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
- the Git collector exposes repository queue wait, parse, fact emission, and commit/projection telemetry
- the Resolution Engine exposes work-item claim, completion/failure, fact-load, and per-stage projection telemetry
- the facts queue exposes backlog depth and oldest-item age by work type and status

Metric labels should stay low-cardinality. Repository ids, run ids, snapshot ids,
and work-item ids belong on spans and structured logs, not on metric labels.
