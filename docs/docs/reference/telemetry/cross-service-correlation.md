# Cross-Service Trace Correlation

PlatformContextGraph runs three services that emit OTEL traces to the same Jaeger backend via an OTEL Collector. This guide shows operators how to correlate traces across service boundaries when debugging end-to-end pipeline behavior.

## Why Traces Don't Automatically Stitch

PCG services communicate asynchronously through Postgres (fact queue, work items, shared projection intents) rather than through direct HTTP or gRPC calls. This means OTEL trace context propagation does not happen automatically via request headers or metadata.

Each service starts its own trace root when it picks up work from the queue or begins a new collection cycle. The traces are separate trees in your trace backend, but they share correlation keys that let you follow an operation end-to-end.

## Service Names

Each service emits traces with a distinct `service.name` resource attribute:

| Service | service.name | Runtime |
|---|---|---|
| API | `platform-context-graph-api` | Python (FastAPI) |
| Ingester | `ingester` | Go |
| Reducer | `reducer` | Go |

All services use `service.namespace = platform-context-graph`.

## Correlation Keys

These keys appear in span attributes, logs, and metrics. Use them to stitch traces across services:

| Key | Where | How to use |
|---|---|---|
| `scope_id` | All services | Links all operations for one repository scope (e.g. `git-repository-scope:<repo_id>`) |
| `generation_id` | Ingester + Reducer | Links one collect cycle through projection and reduction |
| `source_run_id` | Ingester | Links all repositories in one collector run |
| `work_item_id` | Ingester + Reducer | Links one fact work item from enqueue to completion |
| `request_id` | API | Links one API request end-to-end |
| `correlation_id` | API | Links related requests (e.g., MCP session) |
| `pipeline_phase` | All Go services | Filters logs by pipeline stage: `discovery`, `parsing`, `emission`, `projection`, `reduction`, `shared` |
| `domain` | Reducer | Filters by reducer domain: `workload`, `platform`, etc. |

## Cross-Service Trace Stitching Recipes

### Recipe 1: Follow a repository from ingestion to graph

**Goal:** Trace a single repository through the full pipeline from Git collection to graph write.

1. Find the `scope_id` for the repository. If you know the repo path, construct it as `git-repository-scope:<repo_path_hash>`. Otherwise, find it in ingester logs or from the `collector.observe` trace span attributes.
2. Search Jaeger for traces with `scope_id` matching your target value.
3. Filter by `service.name` to separate ingester, reducer, and API activity.
4. You will find separate trace trees:
   - **Ingester**: `collector.observe` → `fact.emit` → `projector.run` → `canonical.write`
   - **Reducer**: `reducer.run` → `canonical.write` (shared projection)
   - **API**: `pcg.http.*` → `pcg.query.*` (if the API queried this repo's data)

Each trace tree is independent, but the shared `scope_id` lets you correlate them.

### Recipe 2: Follow a work item through the queue

**Goal:** Trace a single fact work item from enqueue to projection completion or failure.

1. Find the `work_item_id` from projector or reducer logs. Look for log events like `resolution.work_item.projected`, `resolution.work_item.completed`, or `resolution.work_item.failed`.
2. Search logs (not traces) for all events with that `work_item_id`.
3. Each log event includes a `trace_id` field. Copy the `trace_id` values.
4. Open each `trace_id` in Jaeger to see the corresponding span tree (enqueue, claim, load facts, project, ack).

### Recipe 3: API request to underlying graph query

**Goal:** Trace an API request from the HTTP handler through Neo4j query execution.

1. Start from the API trace (`pcg.http.*` span) in Jaeger.
2. Note the `request_id` span attribute.
3. If the request triggered a Neo4j query, the same `request_id` appears in query logs and traces.
4. Search logs for the `request_id` to find the corresponding query execution events.
5. Use the `trace_id` from the query log to open the query trace in Jaeger.
6. The query trace will include child `pcg.neo4j.query` spans showing Cypher execution timing.

### Recipe 4: Diagnose pipeline phase latency

**Goal:** Isolate slow behavior in a specific pipeline stage (e.g., projection is slow but collection is fine).

1. Filter all logs by `pipeline_phase` to isolate one stage. For example, `pipeline_phase=projection` shows only projector activity.
2. Use `scope_id` to follow a specific repository through that phase.
3. Find the `trace_id` in the logs and open the trace in Jaeger.
4. Compare span timings across different `scope_id` values to see if the slowdown is repo-specific or systemic.

### Recipe 5: Correlate shared projection across domains

**Goal:** Understand why shared projection is slow or stuck for a specific domain (e.g., `workload` or `platform`).

1. Search logs for `pipeline_phase=shared` and the target `domain` (e.g., `domain=workload`).
2. Note the `partition_key` if you want to narrow to a specific partition.
3. Find the `trace_id` from the logs and open the shared projection trace (`canonical.write` span).
4. Inspect child `postgres.query` and `neo4j.execute` spans to see whether latency is in intent loading or graph writes.

## End-to-End Correlation Diagram

```text
API Request (Python)
  service.name: platform-context-graph-api
  trace_id: A, request_id: R1
  └── pcg.http.* (HTTP handler)
      └── pcg.query.* → Neo4j read
          scope_id: S1 (identifies which repo data)

                    ↕ (correlation via scope_id S1)

Ingester (Go)
  service.name: ingester
  trace_id: B, scope_id: S1, generation_id: G1
  ├── collector.observe (discovery + collect)
  │   ├── scope.assign (repo selection)
  │   └── fact.emit → postgres.exec (fact writes)
  └── projector.run (claim + project + ack)
      ├── postgres.query (fact load)
      ├── canonical.write → neo4j.execute (graph write)
      ├── postgres.exec (content write)
      └── reducer_intent.enqueue → postgres.exec (intent write)

                    ↕ (correlation via work_item_id W1 or domain D1)

Reducer (Go)
  service.name: reducer
  trace_id: C, scope_id: S1, domain: workload
  └── reducer.run (claim + execute + ack)
      ├── postgres.query (intent load)
      └── neo4j.execute (graph write)

                    ↕ (correlation via domain + partition_key)

Reducer (Go, shared projection)
  service.name: reducer
  trace_id: D, domain: workload, partition_key: P1
  └── canonical.write (shared projection cycle)
      ├── postgres.query (intent load, lease management)
      └── neo4j.execute (edge writes)
```

## Grafana + Loki Log Correlation

If you are using Grafana with Loki for log aggregation, you can build panels that correlate logs across services using the structured log keys.

### Example LogQL queries

**All logs for a specific repository:**

```logql
{service_name=~"platform-context-graph-api|ingester|reducer"} 
  | json 
  | scope_id="git-repository-scope:my-repo-id"
```

**All logs in the projection phase:**

```logql
{service_name=~"ingester|reducer"} 
  | json 
  | pipeline_phase="projection"
```

**All errors in shared projection for the workload domain:**

```logql
{service_name="reducer"} 
  | json 
  | pipeline_phase="shared" 
  | domain="workload" 
  | level="ERROR"
```

### Logs-to-Traces data link

Configure Grafana's "Logs to Traces" feature to jump from log lines directly into Jaeger:

1. In your Grafana Loki data source settings, add a "Derived Fields" configuration.
2. Set the field name to `trace_id`.
3. Set the regex to extract `trace_id` from JSON logs: `"trace_id":\s*"([^"]+)"`.
4. Configure the data link URL to your Jaeger instance: `https://jaeger.example.com/trace/${__value.raw}`.

Now when you view logs in Grafana, each log line with a `trace_id` will have a clickable link that opens the corresponding trace in Jaeger.

## Grafana Dashboard Patterns

### Cross-service latency waterfall

Build a dashboard with:

- **Panel 1**: `pcg_dp_collector_observe_duration_seconds` (p95) — Ingester collection time
- **Panel 2**: `pcg_dp_projector_run_duration_seconds` (p95) — Ingester projection time
- **Panel 3**: `pcg_dp_reducer_run_duration_seconds` (p95) by domain — Reducer execution time
- **Panel 4**: `pcg_http_request_duration_seconds` (p95) — API request time

This waterfall shows where latency is accumulating across the pipeline.

### Cross-service queue health

Build a dashboard with:

- **Panel 1**: `pcg_fact_queue_depth` by work type — Ingester backlog
- **Panel 2**: `pcg_fact_queue_oldest_age_seconds` — How long work is waiting
- **Panel 3**: `pcg_runtime_queue_depth` by service and stage — Per-service queue depth
- **Panel 4**: `pcg_shared_projection_pending_intents` by domain — Shared projection backlog

This dashboard shows where work is piling up and which service needs attention.

### Scope-level progression

For a specific `scope_id`, track its progression through the pipeline:

1. Use exemplars (if enabled) to jump from metric spikes to traces.
2. Search logs for the `scope_id` to see progression events.
3. Filter traces by `scope_id` span attribute to see all trace trees for that scope.

## Best Practices

- **Start with metrics** to identify which service or phase is slow or failing.
- **Move to logs** to find the `scope_id`, `work_item_id`, or `generation_id` for the affected operation.
- **Jump to traces** using the `trace_id` from the logs to see span-level timing.
- **Use correlation keys** to stitch the separate trace trees back together.
- **Avoid high-cardinality filters** in production. Use `scope_id` for targeted debugging, not as a dashboard dimension.
- **Use pipeline_phase** to filter logs by stage when you know which part of the pipeline is misbehaving.

## Common Pitfalls

### Trace ID is not enough

A `trace_id` only identifies one trace tree from one service. To follow an operation end-to-end, you need a correlation key (`scope_id`, `work_item_id`, etc.) that spans multiple traces.

### Correlation keys are not in every span

Correlation keys appear in span attributes for pipeline spans (`collector.observe`, `projector.run`, `reducer.run`), but not always in dependency spans (`postgres.exec`, `neo4j.execute`). Use the parent span attributes or the logs to find the correlation context.

### service.name filtering is critical

When searching traces by `scope_id`, always filter by `service.name` to separate ingester, reducer, and API activity. Otherwise, you will see an overwhelming jumble of unrelated traces from all three services.

### Logs carry more context than traces

Traces show timing. Logs show context (e.g., failure classification, retry count, domain, partition key). Use both together when debugging incidents.

## When Correlation Fails

If you cannot find a trace or log for an operation:

1. **Check service health**: Is the service running? Use `/health` or `/admin/status`.
2. **Check OTEL export**: Is `OTEL_EXPORTER_OTLP_ENDPOINT` configured? Are traces reaching Jaeger?
3. **Check log filtering**: Are you filtering by the correct `service.name` or `pipeline_phase`?
4. **Check queue state**: Is work stuck in the queue? Use `pcg_fact_queue_depth` and `pcg_runtime_queue_depth` metrics.
5. **Check dead-letter state**: Did the work fail terminally? Search logs for `resolution.work_item.dead_lettered`.
