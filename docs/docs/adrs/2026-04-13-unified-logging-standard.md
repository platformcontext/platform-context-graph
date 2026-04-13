# ADR: Unified JSON Logging Standard

**Status:** Accepted

## Context

PlatformContextGraph runs two runtime stacks that both emit structured JSON
logs:

- **Python (read path)** uses a `StructuredJsonFormatter` that emits fields
  such as `timestamp`, `severity_text`, `message`, `service_name`, and
  `event_name`.
- **Go (write path)** uses `log/slog` with a custom `TraceHandler` that
  historically emitted the default slog field names: `time`, `level`, and `msg`.

The field-name mismatch (`time` vs `timestamp`, `level` vs `severity_text`,
`msg` vs `message`) makes cross-service log correlation harder in Grafana/Loki
and any log aggregation pipeline. Operators writing queries must remember which
runtime produced a given log line and use the correct field name, which is
error-prone during incident response.

Both stacks already carry OTEL trace context and pipeline-specific metadata.
What they lack is a single canonical schema that normalises field names so that
one Loki query can filter by `severity_text`, `component`, or `pipeline_phase`
regardless of the originating runtime.

## Decision

Both the Go and Python runtimes will emit JSON log records that conform to the
canonical field set defined below. The Go `TraceHandler` will rename its
built-in slog keys (`time` -> `timestamp`, `level` -> `severity_text`,
`msg` -> `message`) and inject `component`, `runtime_role`, and
`severity_number` on every record. The Python `StructuredJsonFormatter` already
conforms and requires no changes.

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
The `NewLogger` constructor now accepts `component` and `runtimeRole` as
required parameters and adds them as base attributes on every log line. A new
`EventAttr` helper produces `event_name` attributes. The `severity_number`
field is injected by `TraceHandler.Handle()` when a valid OTEL span context is
present, mapping slog levels to OTEL severity numbers (DEBUG=5, INFO=9,
WARN=13, ERROR=17).

Two new pipeline phase constants (`PhaseQuery`, `PhaseServe`) complete the
phase vocabulary for read-path operations.

### Python Implementation

The existing `StructuredJsonFormatter` already emits all required fields with
the canonical names. No changes are needed.

## Consequences

- **Easier cross-service correlation.** A single Loki query like
  `{service_namespace="platform-context-graph"} | json | severity_text="ERROR"`
  now works regardless of which runtime produced the log line.
- **Consistent Grafana dashboards.** Dashboard variables can use `component`,
  `runtime_role`, and `pipeline_phase` without runtime-specific overrides.
- **Stable contract.** New Go or Python services inherit the schema
  automatically through the shared logging constructors.
- **Minor migration cost.** Existing Loki queries or Grafana panels that
  reference the old Go field names (`time`, `level`, `msg`) must be updated to
  use the canonical names.
