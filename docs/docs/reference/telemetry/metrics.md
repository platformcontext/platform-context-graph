# Telemetry Metrics

This page focuses on metrics that matter for on-call, autoscaling, and performance tuning.

The canonical rules are:

- labels stay low-cardinality
- `repo_id`, `run_id`, `source_snapshot_id`, and `work_item_id` belong on traces and logs, not metrics
- metrics should answer “how much”, “how often”, “how fast”, and “how full”

## How To Read This Page

Each metric entry includes:

- **Type**: counter, histogram, or gauge
- **Description**: what is being measured
- **How to leverage**: how an SRE or performance engineer should use it

## API And MCP

### `pcg_http_requests_total`

- Type: Counter
- Description: Total HTTP requests handled by the API runtime.
- How to leverage: Use as the primary request-rate signal for API traffic baselines and sudden traffic shifts.

### `pcg_http_request_duration_seconds`

- Type: Histogram
- Description: End-to-end HTTP request latency.
- How to leverage: Watch p50/p95/p99 for API regressions and compare against backend query latency to see whether the bottleneck is request handling or downstream storage.

### `pcg_http_request_errors_total`

- Type: Counter
- Description: Count of HTTP requests that returned error status classes.
- How to leverage: Alert on sustained 5xx growth and correlate with trace volume for the same time window.

### `pcg_mcp_requests_total`

- Type: Counter
- Description: Total MCP JSON-RPC requests handled by the MCP runtime.
- How to leverage: Use this to separate agent/tool traffic growth from HTTP traffic growth.

### `pcg_mcp_request_duration_seconds`

- Type: Histogram
- Description: MCP request latency.
- How to leverage: Watch for tail-latency regressions in AI-driven workflows.

### `pcg_mcp_tool_calls_total`

- Type: Counter
- Description: Total MCP tool invocations.
- How to leverage: Use it to identify the busiest tool families and to explain backend load spikes caused by agent traffic.

## Git Collector And Indexing

### `pcg_index_runs_total`

- Type: Counter
- Description: Count of indexing runs by status and finalization status.
- How to leverage: Use for success/failure trend dashboards and deployment regression detection.

### `pcg_index_run_duration_seconds`

- Type: Histogram
- Description: End-to-end indexing run latency.
- How to leverage: The top-line measure for “did the ingest pipeline get slower?”

### `pcg_index_active_runs`

- Type: Gauge
- Description: Current number of active indexing runs.
- How to leverage: Useful for confirming lock behavior and checking whether multiple runs are overlapping unexpectedly.

### `pcg_index_active_repositories`

- Type: Gauge
- Description: Current number of repositories in flight during indexing.
- How to leverage: Compare against configured worker counts to see whether the pipeline is actually saturated.

### `pcg_index_repository_duration_seconds`

- Type: Histogram
- Description: Per-repository end-to-end processing latency.
- How to leverage: Use for repo-class tuning and for finding outlier repositories that dominate wall-clock time.

### `pcg_index_stage_duration_seconds`

- Type: Histogram
- Description: Duration of named indexing stages such as parse wait, parse, commit wait, and commit.
- How to leverage: This is one of the most important tuning metrics. It tells you whether the time is being lost in queueing, parsing, committing, or later phases.

### `pcg_index_snapshot_queue_depth`

- Type: Gauge
- Description: Number of parsed repository snapshots waiting to commit.
- How to leverage: Use for commit-worker sizing and backpressure diagnosis.

### `pcg_index_parse_tasks_active`

- Type: Gauge
- Description: Number of in-flight file parse tasks.
- How to leverage: Helps distinguish “workers are idle” from “workers are saturated.”

## Facts-First Pipeline

### `pcg_fact_records_total`

- Type: Counter
- Description: Number of facts emitted by source system and work type.
- How to leverage: Use for change-volume baselines and to explain downstream projection or storage cost.

### `pcg_fact_emission_duration_seconds`

- Type: Histogram
- Description: Time spent emitting one fact batch from a parsed snapshot.
- How to leverage: Use to detect whether the collector bottleneck moved from parsing into fact serialization or Postgres writes.

### `pcg_fact_work_items_total`

- Type: Counter
- Description: Work-item lifecycle transitions recorded during facts-first ingestion.
- How to leverage: Track enqueued, leased, completed, failed, and lease-miss outcomes to understand work flow and retry behavior.

### `pcg_fact_queue_depth`

- Type: Gauge
- Description: Current fact work-queue depth by work type and queue status.
- How to leverage: Primary autoscaling and backlog metric for the Resolution Engine.

### `pcg_fact_queue_oldest_age_seconds`

- Type: Gauge
- Description: Age of the oldest queued fact work item by work type and queue status.
- How to leverage: Better than raw depth for alerting because it shows whether customers are actually waiting longer, not just whether the queue is non-empty.

### `pcg_fact_store_operations_total`

- Type: Counter
- Description: Count of Postgres fact-store operations by operation and outcome.
- How to leverage: Use to see whether fact persistence volume is dominated by writes or reads, and whether failures are clustering around a specific SQL path.

### `pcg_fact_store_operation_duration_seconds`

- Type: Histogram
- Description: Latency of Postgres fact-store operations such as `upsert_fact_run`, `upsert_facts`, and `list_facts`.
- How to leverage: This is the main metric for deciding whether the facts layer itself is becoming a bottleneck.

### `pcg_fact_store_rows_total`

- Type: Counter
- Description: Total fact rows touched by fact-store operations.
- How to leverage: Use with operation latency to calculate effective throughput and to spot nonlinear scaling.

### `pcg_fact_queue_operations_total`

- Type: Counter
- Description: Count of Postgres fact-queue operations by operation and outcome.
- How to leverage: Helps explain whether queue pressure comes from enqueue volume, claim churn, retries, or completion throughput.

### `pcg_fact_queue_operation_duration_seconds`

- Type: Histogram
- Description: Latency of Postgres fact-queue operations such as enqueue, claim, lease, complete, fail, and queue snapshot reads.
- How to leverage: Use this to detect whether the queue database path is slowing down before backlog becomes obvious.

### `pcg_fact_queue_rows_total`

- Type: Counter
- Description: Total rows returned by queue snapshot or queue read operations.
- How to leverage: Useful for sizing and for understanding whether queue scans are still cheap as volume grows.

## Resolution Engine

### `pcg_resolution_work_items_total`

- Type: Counter
- Description: Resolution work-item outcomes such as completed, failed, or empty poll.
- How to leverage: The top-line success/failure metric for the Resolution Engine.

### `pcg_resolution_work_item_duration_seconds`

- Type: Histogram
- Description: End-to-end duration of one resolution work item.
- How to leverage: Primary latency metric for projection throughput.

### `pcg_resolution_claim_duration_seconds`

- Type: Histogram
- Description: Time spent claiming one work item from the queue.
- How to leverage: Use for queue-contention and autoscaling decisions. Rising claim latency often means queue or database pressure.

### `pcg_resolution_workers_active`

- Type: Gauge
- Description: Number of currently active resolution workers in a process.
- How to leverage: Compare with queue depth and work-item duration to see whether more workers would help or whether the bottleneck is elsewhere.

### `pcg_resolution_idle_sleep_seconds`

- Type: Histogram
- Description: Duration of idle sleeps after empty queue polls.
- How to leverage: Useful for tuning polling behavior and estimating wasted idle time.

### `pcg_resolution_facts_loaded_total`

- Type: Counter
- Description: Number of facts loaded into the Resolution Engine per work item.
- How to leverage: Normalize resolution latency by work size instead of guessing from repository count alone.

### `pcg_resolution_stage_duration_seconds`

- Type: Histogram
- Description: Duration of each projection stage such as `load_facts`, `project_facts`, `project_relationships`, `project_workloads`, and `project_platforms`.
- How to leverage: Best metric for deciding where projection time is really going.

### `pcg_resolution_stage_output_total`

- Type: Counter
- Description: Output volume attributed to each projection stage.
- How to leverage: Compare stage duration with stage output to find expensive low-yield stages.

### `pcg_resolution_stage_failures_total`

- Type: Counter
- Description: Stage failures grouped by stage name and error class.
- How to leverage: This is the key stage-level incident triage metric. It tells you which stage is breaking and whether failures are dominated by one error class.

## Graph And Storage

### `pcg_graph_write_batch_duration_seconds`

- Type: Histogram
- Description: Graph write batch latency by batch type and entity label.
- How to leverage: Use to tune batch sizes and to spot which entity families are expensive to persist.

### `pcg_graph_write_batch_rows`

- Type: Histogram
- Description: Batch size distribution for graph writes.
- How to leverage: Compare with batch latency to tune write thresholds and chunk sizes.

### `pcg_neo4j_query_duration_seconds`

- Type: Histogram
- Description: Neo4j query latency by operation type.
- How to leverage: Main signal for graph database latency and query-level regressions.

### `pcg_neo4j_query_errors_total`

- Type: Counter
- Description: Neo4j query failures by operation type.
- How to leverage: Use for immediate incident alerting and for identifying unstable query classes.

### `pcg_content_provider_requests_total`

- Type: Counter
- Description: Content provider requests across Postgres and workspace fallback.
- How to leverage: Helps explain content-store load and fallback frequency.

### `pcg_content_provider_duration_seconds`

- Type: Histogram
- Description: Content-provider latency by backend and operation.
- How to leverage: Use to see whether content retrieval is affecting request latency or indexing completion.

### `pcg_content_workspace_fallback_total`

- Type: Counter
- Description: Count of content requests that fell back from Postgres to the workspace.
- How to leverage: Use to detect when the content store is incomplete or unhealthy.

## Tuning Recipes

### Autoscaling The Resolution Engine

Use these together:

- `pcg_fact_queue_depth`
- `pcg_fact_queue_oldest_age_seconds`
- `pcg_resolution_workers_active`
- `pcg_resolution_work_item_duration_seconds`
- `pcg_resolution_claim_duration_seconds`

If queue age is rising while workers stay saturated, scale workers. If queue age is rising but claim latency is also rising, investigate Postgres queue contention before scaling workers blindly.

### Tuning Postgres Fact Throughput

Use these together:

- `pcg_fact_store_operation_duration_seconds`
- `pcg_fact_store_rows_total`
- `pcg_fact_queue_operation_duration_seconds`
- `pcg_fact_queue_depth`

If rows per second drops while queue age rises, the fact store or queue is the likely bottleneck.

### Tuning Neo4j Projection

Use these together:

- `pcg_resolution_stage_duration_seconds`
- `pcg_resolution_stage_output_total`
- `pcg_graph_write_batch_duration_seconds`
- `pcg_graph_write_batch_rows`
- `pcg_neo4j_query_duration_seconds`

If stage output is flat but duration rises, look at graph batch size, Cypher cost, or database contention.

