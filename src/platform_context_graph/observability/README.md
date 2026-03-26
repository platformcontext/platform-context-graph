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
