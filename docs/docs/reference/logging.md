# Logging Standard

For the operator-facing logs guide, see [Telemetry Logs](telemetry/logs.md).

PlatformContextGraph writes one JSON document per log line everywhere: API, MCP, ingester, Falkor worker, and local CLI commands.

That is the standard on purpose. We want logs that are easy to ship, easy to parse, and easy to turn into dashboards without writing a custom parser for every service.

## Canonical Envelope

Every log record uses the same top-level keys:

- `timestamp`
- `severity_text`
- `severity_number`
- `message`
- `event_name`
- `logger_name`
- `service_name`
- `service_namespace`
- `service_version`
- `deployment_environment`
- `component`
- `transport`
- `runtime_role`
- `trace_id`
- `span_id`
- `request_id`
- `correlation_id`
- `exception_type`
- `exception_message`
- `exception_stacktrace`
- `extra_keys`

Rules:

- `timestamp` is UTC RFC3339 with milliseconds
- `extra_keys` is always present and always an object
- custom dimensions belong under `extra_keys`, not as ad hoc top-level keys
- reserved top-level keys are owned by the platform and cannot be overridden by call-site extras
- `message` stays human-readable, but `event_name` is the stable machine key
- stack traces stay inside one JSON record instead of spilling into multiline output

The common fields are there so Loki, Elasticsearch, Grafana, or anything else that understands JSON can index the same shape every time:

- `service_name`, `service_namespace`, and `service_version` identify the runtime
- `component` and `transport` identify where the log came from
- `runtime_role` tells you whether the process is acting as the API, the internal `ingester` runtime role used by the ingester service, the worker, or the CLI
- `trace_id` and `span_id` let you jump from logs into the matching Jaeger trace
- `request_id` and `correlation_id` keep a request together across boundaries

## Why `extra_keys` Exists

We still need room for operation-specific data, just not in a way that turns the log schema into a moving target.

Use `extra_keys` for things like:

- `repo_id`
- `repo_slug`
- `repo_path`
- `run_id`
- `phase`
- `batch_type`
- `rows`
- `duration_seconds`
- `backend`
- `tool_name`
- `query_name`

This keeps dashboards stable. The envelope stays fixed, and the custom dimensions remain queryable.

## Trace Correlation

If a log is emitted inside an active OTEL span, it automatically carries:

- `trace_id`
- `span_id`

Request boundaries also attach:

- `request_id`
- `correlation_id`

Current behavior:

- HTTP honors inbound `X-Request-ID` and generates one when it is missing
- HTTP echoes `X-Request-ID` back in the response
- MCP uses the JSON-RPC request ID when present and generates one otherwise
- `correlation_id` defaults to `request_id` unless an upstream correlation ID is already available

Jaeger is the right place to inspect the shape and timing of a slow request. Use the trace to find the slow span, then use the matching log lines to see the request-specific details.

## Event Names

Keep the message readable, but treat `event_name` as the stable machine key.

Good examples:

- `http.request.completed`
- `mcp.request.received`
- `mcp.tool.completed`
- `graph.batch.entity.flush`
- `bundle.import.failed`

The message can change. `event_name` should not drift casually.

## Ingestion Correlation

Indexing and repository-ingestion logs are easiest to group by these stable
event families:

- `index.discovery.*`
- `index.parse.*`
- `index.repository.*`
- `index.finalization.*`
- `admin.refinalize.*`
- `indexing.repository_coverage.published`

The most useful `extra_keys` fields for Grafana and Loki correlation are
`run_id`, `repo_id`, `repo_name`, `repo_path`, `phase`, `status`, and
`duration_seconds`. When you need the span and metric map, use
[Ingestion Observability](ingestion-observability.md).

Status and recovery reads use the HTTP request log plus those finalization
families. `GET /api/v0/index-status` and `GET /api/v0/index-runs/{run_id}` do
not need a separate log family of their own.

## Example

```json
{
  "timestamp": "2026-03-25T21:14:33.482Z",
  "severity_text": "INFO",
  "severity_number": 9,
  "message": "HTTP request completed for GET /api/v0/repositories/{repo_id:path}/context",
  "event_name": "http.request.completed",
  "logger_name": "platform_context_graph.observability.runtime",
  "service_name": "platform-context-graph-api",
  "service_namespace": "platformcontext",
  "service_version": "0.0.31",
  "deployment_environment": "qa",
  "component": "api",
  "transport": "http",
  "runtime_role": "api",
  "trace_id": "5b2c4f1f0f0b54f8b7c1fb85ac20fd68",
  "span_id": "f1a4e1f0c3139f0a",
  "request_id": "req-http-123",
  "correlation_id": "req-http-123",
  "exception_type": null,
  "exception_message": null,
  "exception_stacktrace": null,
  "extra_keys": {
    "http_method": "GET",
    "http_route": "/api/v0/repositories/{repo_id:path}/context",
    "http_status_code": 200,
    "duration_seconds": 0.041352
  }
}
```

## Operational Notes

- Keep `PCG_LOG_FORMAT=json` in deployed environments.
- Use `text` only when you are debugging locally and raw JSON is getting in the way.
- The old file sinks still exist for compatibility, but they now write the same structured JSON shape instead of a separate plaintext format.
- OTEL logs export is not required for this setup. JSON stdout is the canonical log transport.
