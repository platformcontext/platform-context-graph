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

### `pcg_investigations_total`

- Type: Counter
- Description: Total completed service investigations by intent, deployment mode, and outcome.
- How to leverage: Use this to understand how often operators are asking deployment, network, or dependency questions and whether those investigations are succeeding or erroring.

### `pcg_investigation_duration_seconds`

- Type: Histogram
- Description: End-to-end latency of the investigation query wrapper.
- How to leverage: Watch p95 and p99 when repo widening or downstream query fan-out grows. Compare it to `pcg_http_request_duration_seconds` and `pcg_mcp_tool_duration_seconds` to separate transport overhead from investigation work.

### `pcg_investigation_coverage_total`

- Type: Counter
- Description: Investigation result-quality classifications by intent, deployment mode, and whether evidence was missing.
- How to leverage: This is the top-line signal for sparse versus single-plane versus multi-plane investigation quality. Alert or dashboard on sustained sparse outcomes for important services.

### `pcg_investigation_repositories_considered`

- Type: Histogram
- Description: Number of repositories considered during one investigation.
- How to leverage: Use this to tune repo-widening breadth. Rising breadth with flat quality often means the widening heuristic is getting noisy.

### `pcg_investigation_repositories_with_evidence`

- Type: Histogram
- Description: Number of widened repositories that contributed evidence to one investigation.
- How to leverage: Compare this to `pcg_investigation_repositories_considered` to see whether widening is productive or mostly dead ends.

## Go Runtime Admin Surfaces

### `pcg_runtime_info`

- Type: Gauge
- Description: Presence metric for one mounted Go runtime metrics endpoint, labeled by service name and namespace.
- How to leverage: Use it as the anchor series for dashboards and to confirm that scrape targets are alive before trusting the rest of the runtime panel.

### `pcg_runtime_health_state`

- Type: Gauge
- Description: One-hot health verdict from the shared `/admin/status` reader, labeled by service name and health state.
- How to leverage: Alert on `degraded` or `stalled`, and use it to separate runtime-level pressure from broader platform incidents.

### `pcg_runtime_scope_active`, `pcg_runtime_scope_changed`, `pcg_runtime_scope_unchanged`

- Type: Gauge
- Description: Scope lifecycle counters derived from the status reader, including how many scopes are active, how many have a newer pending generation, and how many remain unchanged.
- How to leverage: Watch the `changed` versus `unchanged` mix during incremental refresh runs to see whether a collector is producing mostly no-op reruns or real churn.

### `pcg_runtime_generation_total`

- Type: Gauge
- Description: Generation lifecycle totals labeled by service name and generation state.
- How to leverage: Pair this with the scope activity gauges to see whether changed scopes are draining into `active`, `superseded`, or `failed` generations as expected during incremental refresh or replay-heavy workloads.

### `pcg_runtime_refresh_skipped_total`

- Type: Counter
- Description: Total refreshes skipped because the collector observed no meaningful change for a scope.
- How to leverage: Use it to validate incremental-refresh effectiveness and to quantify avoided downstream projector or reducer work.

### `pcg_runtime_retry_policy_max_attempts`

- Type: Gauge
- Description: Effective bounded retry budget for each runtime stage, labeled by service name and stage.
- How to leverage: Keep this on the same dashboard as retrying and failed queue items so operators can tell whether a service is behaving badly or simply configured too aggressively.

### `pcg_runtime_retry_policy_retry_delay_seconds`

- Type: Gauge
- Description: Effective retry delay for each runtime stage, labeled by service name and stage.
- How to leverage: Use it to tune recovery behavior for Kubernetes and compose deployments without guessing which retry policy a pod is actually running.

### `pcg_runtime_queue_*`

- Type: Gauge family
- Description: Shared queue depth, pending, in-flight, retrying, succeeded, dead-letter, legacy-failed, overdue-claim, and oldest-outstanding-age metrics for the runtime work queue.
- How to leverage: This is the first dashboard to open when a runtime feels slow. It tells you whether the service is starved, saturated, retrying, or simply draining cleanly.

### `pcg_runtime_stage_items`

- Type: Gauge
- Description: Per-stage work-item counts labeled by stage and queue status.
- How to leverage: Use it to spot whether pressure is concentrated in collector, projector, or reducer behavior instead of treating the whole data plane as one opaque backlog.

### `pcg_runtime_domain_outstanding`, `pcg_runtime_domain_retrying`, `pcg_runtime_domain_dead_letter`, `pcg_runtime_domain_failed`, `pcg_runtime_domain_oldest_age_seconds`

- Type: Gauge family
- Description: Domain-specific backlog and age metrics for runtime work that fans out by reducer or projection domain, including explicit dead-letter pressure alongside any legacy failed rows.
- How to leverage: These metrics are the operator-facing answer to “which slice of the platform is actually stuck?” and are especially useful once more ingestors and reducers land.

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

### `pcg_resolution_failure_classifications_total`

- Type: Counter
- Description: Count of classified Resolution Engine failures by failure class and retry disposition.
- How to leverage: Use this to separate retryable timeouts from input bugs or dependency outages before deciding whether to replay, scale, or rollback.

### `pcg_projection_decisions_total`

- Type: Counter
- Description: Count of persisted projection decisions by decision type and confidence band.
- How to leverage: Watch for sudden changes in decision mix or confidence distribution after parser, resolution, or workload/platform changes.

### `pcg_projection_confidence_score`

- Type: Histogram
- Description: Distribution of persisted projection confidence scores.
- How to leverage: Use this to detect semantic drift. A falling confidence distribution is often the first sign that evidence quality degraded before graph correctness visibly breaks.

### `pcg_projection_decision_evidence_total`

- Type: Counter
- Description: Count of bounded evidence rows attached to persisted projection decisions.
- How to leverage: Correlate with decision volume to understand whether resolution is becoming more inference-heavy or more directly fact-backed.

### `pcg_admin_fact_actions_total`

- Type: Counter
- Description: Count of admin fact actions such as replay, work-item listing, dead-letter, backfill requests, and replay-event inspection.
- How to leverage: Use this as an operator-intervention signal during incidents and as an audit-friendly indicator that a recovery workflow is being exercised.

## Projection Hot Paths

### `pcg_resolution_file_projection_batch_duration_seconds`

- Type: Histogram
- Description: Duration of each bounded file-projection batch inside the facts-first projection path.
- How to leverage: Use this to see whether giant repos are slowing down in file/content projection before relationship or workload stages even start.

### `pcg_resolution_file_projection_batch_files_total`

- Type: Counter
- Description: Total file facts processed through bounded file-projection batches.
- How to leverage: Pair the rate of this metric with `pcg_resolution_file_projection_batch_duration_seconds` to estimate effective file projection throughput.

### `pcg_resolution_directory_flush_rows_total`

- Type: Counter
- Description: Total directory-chain and containment rows flushed during file projection, labeled by `pcg.row_kind`.
- How to leverage: Useful for spotting repos whose directory fan-out makes containment writes disproportionately expensive.

### `pcg_content_file_batch_upsert_duration_seconds`

- Type: Histogram
- Description: Duration of chunked Postgres file-content upsert batches.
- How to leverage: Use this to separate slow file projection from slow content-store writes, especially when Postgres IO or WAL pressure rises.

### `pcg_content_file_batch_upsert_rows_total`

- Type: Counter
- Description: Total file-content rows written through chunked Postgres upsert batches.
- How to leverage: Compare the rate of this metric with the corresponding duration histogram to see whether chunking improved content-store throughput.

### `pcg_call_prefilter_known_name_scan_duration_seconds`

- Type: Histogram
- Description: Duration of known-callable-name scans used by CALLS prefiltering, labeled by scan variant.
- How to leverage: If relationship projection slows down before actual edge creation, this tells you whether the name-scan phase is the culprit.

### `pcg_call_prep_calls_inspected_total`

- Type: Counter
- Description: Total raw call records inspected during call-row preparation, labeled by language.
- How to leverage: Use it to quantify how much relationship work each language family is actually driving during large-repo runs.

### `pcg_call_prep_calls_capped_total`

- Type: Counter
- Description: Total raw call records skipped because `PCG_MAX_CALLS_PER_FILE` capped preparation work.
- How to leverage: Rising values mean the cap is actively protecting stability. Use it alongside correctness checks before deciding to raise the cap.

### `pcg_inheritance_batch_duration_seconds`

- Type: Histogram
- Description: Duration of batched inheritance and interface flushes.
- How to leverage: Useful for identifying when inheritance fan-out, especially in C# or class-heavy repos, starts dominating relationship time.

### `pcg_inheritance_batch_rows_total`

- Type: Counter
- Description: Total inheritance and interface rows flushed, labeled by batch mode.
- How to leverage: Pair with the inheritance duration histogram to see whether slower batches are simply larger or genuinely less efficient.

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

## Go Data Plane Metrics

The Go data plane emits OTEL metrics via the `go/internal/telemetry` package. All
metric names use the `pcg_dp_` prefix to differentiate from the Python `pcg_`
namespace. The hand-rolled `pcg_runtime_*` status gauges documented above are
preserved alongside the new OTEL metrics on the same `/metrics` endpoint via a
composite handler.

### Counters

### `pcg_dp_facts_emitted_total`

- Type: Counter
- Description: Total facts emitted by the collector during snapshot collection.
- Dimensions: `scope_id`, `source_system`, `collector_kind`
- How to leverage: Use as the top-line ingestion volume signal. Compare with `pcg_dp_facts_committed_total` to detect emission-to-commit drop-off.

### `pcg_dp_facts_committed_total`

- Type: Counter
- Description: Total facts durably committed to the Postgres fact store.
- Dimensions: `scope_id`, `source_system`, `collector_kind`
- How to leverage: If this diverges from `pcg_dp_facts_emitted_total`, the commit path is failing or dropping work.

### `pcg_dp_projections_completed_total`

- Type: Counter
- Description: Total projection cycles completed by the projector.
- Dimensions: `scope_id`, `status` (`succeeded` or `failed`)
- How to leverage: Primary success/failure signal for the Go projector. Alert on rising `failed` count.

### `pcg_dp_reducer_intents_enqueued_total`

- Type: Counter
- Description: Total reducer intents enqueued after projection.
- Dimensions: `scope_id`
- How to leverage: Tracks how much downstream reducer work each projection cycle generates.

### `pcg_dp_reducer_executions_total`

- Type: Counter
- Description: Total reducer intent executions.
- Dimensions: `domain`, `status` (`succeeded` or `failed`)
- How to leverage: Top-line reducer throughput and failure signal, segmented by domain.

### `pcg_dp_canonical_writes_total`

- Type: Counter
- Description: Total canonical graph write batches to Neo4j.
- Dimensions: `scope_id` or `domain`
- How to leverage: Track graph write volume. Pair with `pcg_dp_canonical_write_duration_seconds` for throughput analysis.

### `pcg_dp_shared_projection_cycles_total`

- Type: Counter
- Description: Total shared projection partition cycles across all domains.
- Dimensions: `domain`, `partition_key`
- How to leverage: Track shared projection activity by domain to detect stuck or overloaded partitions.

### Histograms

### `pcg_dp_collector_observe_duration_seconds`

- Type: Histogram
- Description: Duration of one collector observe cycle (discovery + snapshot + commit).
- Unit: seconds
- Custom buckets: 0.01, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60
- How to leverage: Primary latency signal for the Git collector. Watch p95 for regression detection.

### `pcg_dp_scope_assign_duration_seconds`

- Type: Histogram
- Description: Duration of repository discovery and scope assignment.
- Unit: seconds
- Dimensions: `collector_kind`, `source_system`
- How to leverage: Separates discovery time from snapshot time inside the collector cycle.

### `pcg_dp_fact_emit_duration_seconds`

- Type: Histogram
- Description: Duration of fact emission for one repository (snapshot + fact building).
- Unit: seconds
- Dimensions: `collector_kind`, `source_system`, `scope_id`
- How to leverage: Identifies slow repositories at the per-repo level before they inflate the overall collector duration.

### `pcg_dp_projector_run_duration_seconds`

- Type: Histogram
- Description: Duration of one projector claim-load-project-ack cycle.
- Unit: seconds
- Custom buckets: 0.1, 0.5, 1, 2.5, 5, 10, 30, 60, 120
- How to leverage: Primary latency signal for the Go projector work loop.

### `pcg_dp_projector_stage_duration_seconds`

- Type: Histogram
- Description: Duration of individual projector stages (graph write, content write, intent enqueue).
- Unit: seconds
- Dimensions: `scope_id`
- How to leverage: Breaks down where time is spent within a single projection cycle.

### `pcg_dp_reducer_run_duration_seconds`

- Type: Histogram
- Description: Duration of one reducer claim-execute-ack cycle.
- Unit: seconds
- Dimensions: `domain`
- How to leverage: Primary latency signal for reducer intent execution, segmented by domain.

### `pcg_dp_canonical_write_duration_seconds`

- Type: Histogram
- Description: Duration of canonical graph writes to Neo4j.
- Unit: seconds
- Dimensions: `scope_id` or `domain`
- How to leverage: Shows whether Neo4j write latency is the bottleneck in projection or shared projection.

### `pcg_dp_queue_claim_duration_seconds`

- Type: Histogram
- Description: Duration of work-item claims from the Postgres work queue.
- Unit: seconds
- Dimensions: `queue` (`projector` or `reducer`)
- How to leverage: Rising claim latency often indicates Postgres queue contention before backlog becomes visible.

### `pcg_dp_postgres_query_duration_seconds`

- Type: Histogram
- Description: Duration of every Postgres query executed through the instrumented database wrapper.
- Unit: seconds
- Custom buckets: 0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5
- Dimensions: `operation` (`read` or `write`), `store` (e.g. `ingester`, `reducer`, `bootstrap-index`)
- How to leverage: The most granular Postgres performance signal. Use to detect slow queries, connection pressure, or per-store hotspots before they surface as pipeline backlog.

### `pcg_dp_neo4j_query_duration_seconds`

- Type: Histogram
- Description: Duration of every Neo4j Cypher statement executed through the instrumented executor wrapper.
- Unit: seconds
- Dimensions: `operation` (`write`)
- How to leverage: Shows Neo4j write latency at the individual statement level. Pair with `pcg_dp_canonical_write_duration_seconds` to see whether batch overhead or individual statement cost dominates.

### Go Data Plane Tuning Recipes

#### Database Performance Diagnosis

Use these together:

- `pcg_dp_postgres_query_duration_seconds` (by store and operation)
- `pcg_dp_neo4j_query_duration_seconds`
- `pcg_dp_queue_claim_duration_seconds`
- `pcg_dp_canonical_write_duration_seconds`

If Postgres query duration rises while queue claim stays flat, investigate specific
stores. If both rise together, suspect Postgres connection saturation.

#### Collector Throughput

Use these together:

- `pcg_dp_collector_observe_duration_seconds`
- `pcg_dp_scope_assign_duration_seconds`
- `pcg_dp_fact_emit_duration_seconds`
- `pcg_dp_facts_emitted_total`
- `pcg_dp_facts_committed_total`

If collector duration rises, check whether discovery (`scope_assign`) or per-repo
snapshot (`fact_emit`) is the bottleneck.

#### End-to-End Pipeline Health

Use these together:

- `pcg_dp_facts_emitted_total` (rate)
- `pcg_dp_projections_completed_total` (rate by status)
- `pcg_dp_reducer_executions_total` (rate by status)
- `pcg_dp_shared_projection_cycles_total` (rate)

If emitted facts rate is healthy but projection or reducer rates drop, the
bottleneck is downstream. Use the per-stage histograms to pinpoint the slowdown.
