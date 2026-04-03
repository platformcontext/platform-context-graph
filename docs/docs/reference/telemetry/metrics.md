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

### `pcg_mcp_request_errors_total`

- Type: Counter
- Description: Count of MCP requests that completed with an error outcome.
- How to leverage: Alert on tool-serving instability separately from HTTP API health.

### `pcg_mcp_tool_calls_total`

- Type: Counter
- Description: Total MCP tool invocations.
- How to leverage: Use it to identify the busiest tool families and to explain backend load spikes caused by agent traffic.

### `pcg_mcp_tool_duration_seconds`

- Type: Histogram
- Description: End-to-end latency of individual MCP tool calls.
- How to leverage: Use this to pinpoint whether MCP latency is broad request overhead or concentrated in specific tool families.

### `pcg_mcp_tool_errors_total`

- Type: Counter
- Description: MCP tool failures grouped by tool name and error outcome.
- How to leverage: Use it to identify unstable tools before they show up as broad MCP request regressions.

## Git Collector And Indexing

### `pcg_index_runs_total`

- Type: Counter
- Description: Count of indexing runs by status and finalization status.
- How to leverage: Use for success/failure trend dashboards and deployment regression detection.

### `pcg_index_run_duration_seconds`

- Type: Histogram
- Description: End-to-end indexing run latency.
- How to leverage: The top-line measure for “did the ingest pipeline get slower?”

### `pcg_index_repositories_total`

- Type: Counter
- Description: Count of repositories processed during indexing runs.
- How to leverage: Use with run duration to normalize throughput by repository volume instead of raw wall-clock time.

### `pcg_index_checkpoints_total`

- Type: Counter
- Description: Count of indexing checkpoint lifecycle events.
- How to leverage: Use this to detect resume-heavy runs, checkpoint churn, or unexpected restart behavior.

### `pcg_index_active_runs`

- Type: Gauge
- Description: Current number of active indexing runs.
- How to leverage: Useful for confirming lock behavior and checking whether multiple runs are overlapping unexpectedly.

### `pcg_index_active_repositories`

- Type: Gauge
- Description: Current number of repositories in flight during indexing.
- How to leverage: Compare against configured worker counts to see whether the pipeline is actually saturated.

### `pcg_index_checkpoint_pending_repositories`

- Type: Gauge
- Description: Number of repositories still pending inside a checkpointed run.
- How to leverage: This is the cleanest “how much ingest work is left?” signal when resume/checkpoint mode is active.

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

### `pcg_hidden_dirs_skipped_total`

- Type: Counter
- Description: Count of hidden directories skipped during discovery.
- How to leverage: Useful when file-count drift or unexpectedly small snapshots might be explained by ignore behavior rather than parser regressions.

### `pcg_index_lock_contention_skips_total`

- Type: Counter
- Description: Count of indexing attempts skipped because a repo lock was already held.
- How to leverage: Use this to detect operational overlap or scheduling issues rather than treating reduced throughput as a parser/database problem.

### `pcg_ingester_scan_requests_total`

- Type: Counter
- Description: Count of ingester scan-loop requests for repository discovery/sync.
- How to leverage: Use this to separate sync cadence from actual indexing throughput.

### `pcg_index_repo_graph_write_duration_seconds`

- Type: Histogram
- Description: Per-repository graph-write latency within indexing.
- How to leverage: Use it to separate parse bottlenecks from graph persistence bottlenecks.

### `pcg_index_repo_content_write_duration_seconds`

- Type: Histogram
- Description: Per-repository content-store write latency within indexing.
- How to leverage: Useful when the content store becomes the slow tail instead of graph projection.

### `pcg_index_fallback_resolution_total`

- Type: Counter
- Description: Count of fallback symbol/call resolution outcomes during indexing.
- How to leverage: Rising fallback rates often indicate quality drift that can later become performance waste or incorrect edges.

### `pcg_index_ambiguous_resolution_total`

- Type: Counter
- Description: Count of ambiguous resolution outcomes during indexing.
- How to leverage: Use this as a semantic-quality metric when tuning call and relationship resolution.

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

### `pcg_fact_postgres_pool_size`

- Type: Gauge
- Description: Current configured connection count for the fact-store or fact-queue psycopg pool.
- How to leverage: Confirms whether the service is actually running with the pool size you intended before you start blaming Postgres or worker count.

### `pcg_fact_postgres_pool_available`

- Type: Gauge
- Description: Current number of immediately available connections in the fact-store or fact-queue pool.
- How to leverage: If this stays near zero while backlog or latency rises, the service is connection-starved rather than compute-starved.

### `pcg_fact_postgres_pool_in_use`

- Type: Gauge
- Description: Current number of borrowed connections in the fact-store or fact-queue pool.
- How to leverage: Use it with `pcg_fact_postgres_pool_waiting` to decide whether to increase pool size or reduce concurrent workers.

### `pcg_fact_postgres_pool_waiting`

- Type: Gauge
- Description: Current number of callers waiting for a fact-store or fact-queue pool connection.
- How to leverage: This is the clearest pool-saturation metric. If it rises, you are already contending on Postgres access before queue age fully shows it.

### `pcg_fact_postgres_pool_acquire_duration_seconds`

- Type: Histogram
- Description: Time spent waiting to borrow a connection from the fact-store or fact-queue pool.
- How to leverage: Use this to distinguish “slow SQL” from “slow connection acquisition.”

### `pcg_fact_queue_retry_age_seconds`

- Type: Histogram
- Description: Age of a retried work item when it is claimed again.
- How to leverage: Rising retry age means retry traffic is starving behind fresh work or a bottleneck is preventing retries from making progress.

### `pcg_fact_queue_dead_letters_total`

- Type: Counter
- Description: Count of work items sent to terminal failed state after exhausting retry attempts.
- How to leverage: This is the top-line dead-letter signal for the facts-first pipeline and should page quickly if it rises unexpectedly.

### `pcg_fact_queue_dead_letter_age_seconds`

- Type: Histogram
- Description: Age of a work item when it becomes terminally failed.
- How to leverage: Use it to decide whether work is failing fast because of bad inputs or failing late after expensive wasted retries.

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

## Host And Runtime Capacity

### `pcg_process_rss_bytes`

- Type: Gauge
- Description: Current resident memory of the running process.
- How to leverage: Use this for memory-right-sizing and to detect runaway service growth before the container is OOM-killed.

### `pcg_cgroup_memory_bytes`

- Type: Gauge
- Description: Current cgroup memory usage in bytes.
- How to leverage: Use this as the container-level memory truth during autoscaling and production incident response.

### `pcg_cgroup_memory_limit_bytes`

- Type: Gauge
- Description: Configured cgroup memory limit in bytes.
- How to leverage: Pair this with `pcg_cgroup_memory_bytes` to compute headroom and identify when memory pressure, not CPU, should drive scaling or tuning.

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
- `pcg_fact_postgres_pool_waiting`
- `pcg_fact_postgres_pool_acquire_duration_seconds`

If rows per second drops while queue age rises, the fact store or queue is the likely bottleneck. If pool waiting or acquire duration also rises, fix connection saturation before tuning SQL itself.

### Tuning Neo4j Projection

Use these together:

- `pcg_resolution_stage_duration_seconds`
- `pcg_resolution_stage_output_total`
- `pcg_graph_write_batch_duration_seconds`
- `pcg_graph_write_batch_rows`
- `pcg_neo4j_query_duration_seconds`

If stage output is flat but duration rises, look at graph batch size, Cypher cost, or database contention.
