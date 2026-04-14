# ADR: Unified JSON Logging Standard

**Status:** Accepted

## Context

PlatformContextGraph now runs a Go-owned platform end to end, but the logging
contract still matters because it must stay consistent across API, MCP,
ingester, bootstrap, and resolution-engine processes.

Before the final cutover, Go and Python emitted similar structured logs with
different field names. This ADR locked the canonical field names during the
migration so the rewritten platform could keep one stable operator-facing
schema instead of carrying runtime-specific query rules forward.

## Decision

Every Go-owned runtime emits JSON log records that conform to the canonical
field set defined below. The shared Go `TraceHandler` renames the built-in slog
keys (`time` -> `timestamp`, `level` -> `severity_text`,
`msg` -> `message`) and injects `component`, `runtime_role`, and
`severity_number` on every record.

### Canonical Schema

| Field | Type | Required | Description |
|---|---|---|---|
| `timestamp` | string (ISO8601Z) | yes | Event time in UTC |
| `severity_text` | string | yes | DEBUG, INFO, WARN, or ERROR |
| `severity_number` | int | no | OTEL severity number (5, 9, 13, 17) |
| `message` | string | yes | Human-readable log message |
| `event_name` | string | no | Machine-readable event identifier |
| `service_name` | string | yes | Runtime service name |
| `service_namespace` | string | yes | `platform-context-graph` |
| `service_version` | string | no | Build version |
| `component` | string | yes | Logical component (collector, projector, reducer, api, mcp, query) |
| `transport` | string | no | http, grpc, queue |
| `runtime_role` | string | yes | ingester, reducer, api, bootstrap-index |
| `trace_id` | string | no | OTEL trace ID (present when span is active) |
| `span_id` | string | no | OTEL span ID (present when span is active) |
| `request_id` | string | no | Request correlation |
| `correlation_id` | string | no | Cross-service correlation |
| `pipeline_phase` | string | no | discovery, parsing, emission, projection, reduction, shared, query, serve |
| `scope_id` | string | no | Ingestion scope ID |
| `generation_id` | string | no | Scope generation ID |
| `source_system` | string | no | Origin system (git) |
| `domain` | string | no | Reducer/projection domain |
| `failure_class` | string | no | terminal, retryable, or transient |
| `exception_type` | string | no | Exception class name |
| `exception_message` | string | no | Exception message |
| `exception_stacktrace` | string | no | Full stack trace |
| `extra_keys` | object | no | Additional context fields |

### Go Implementation

The Go `TraceHandler` uses `slog.HandlerOptions.ReplaceAttr` to rename the
three built-in keys and format `timestamp` as RFC3339 with a UTC `Z` suffix.
The `NewLogger` constructor accepts `component` and `runtimeRole` as required
parameters and adds them as base attributes on every log line. The
`severity_number` field is injected by `TraceHandler.Handle()` when a valid
OTEL span context is present, mapping slog levels to OTEL severity numbers
(DEBUG=5, INFO=9, WARN=13, ERROR=17).

## Consequences

- **Easier cross-service correlation.** A single Loki query like
  `{service_namespace="platform-context-graph"} | json | severity_text="ERROR"`
  works across the Go-owned platform without service-specific field mapping.
- **Consistent Grafana dashboards.** Dashboard variables can use `component`,
  `runtime_role`, and `pipeline_phase` without runtime-specific overrides.
- **Stable contract.** New Go services inherit the schema automatically
  through the shared logging constructors.
- **Historical migration note.** This ADR remains the record of the field-name
  normalization completed during the Python-to-Go cutover. The branch no longer
  carries a Python runtime implementation of this contract.
