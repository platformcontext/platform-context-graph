# Telemetry Metrics

This page documents the current Go metric surface that operators can rely on
today. It intentionally focuses on the metrics that exist in code and that are
useful for runtime health, backlog management, throughput tracking, and storage
pressure.

## Reading The Metrics

- Runtime metrics come from the shared `/metrics` surface mounted by each
  long-running runtime.
- Data-plane metrics come from the Go telemetry instruments used by collector,
  projector, reducer, shared follow-up, and storage paths.
- High-cardinality identifiers such as `repo_id`, `run_id`, `scope_id`, and
  `work_item_id` belong in traces and logs, not in metric labels.

## Runtime Health And Backlog

These metrics come from the shared runtime status reader and exist on the API,
MCP server, ingester, and reducer metrics endpoints.

### `pcg_runtime_info`

- Type: Gauge
- Meaning: Presence metric for one runtime endpoint, labeled by
  `service_name` and `service_namespace`.
- Use it for: Dashboard anchoring and scrape-target sanity checks.

### `pcg_runtime_health_state`

- Type: Gauge
- Meaning: One-hot health verdict by `service_name` and `state`
  (`healthy`, `progressing`, `degraded`, `stalled`).
- Use it for: Alerting and quick runtime triage.

### `pcg_runtime_scope_active`
### `pcg_runtime_scope_changed`
### `pcg_runtime_scope_unchanged`

- Type: Gauge
- Meaning: Scope activity and incremental-refresh mix for a runtime.
- Use them for: Distinguishing real scope churn from no-op refresh cycles.

### `pcg_runtime_refresh_skipped_total`

- Type: Counter
- Meaning: Refreshes skipped because the runtime observed no meaningful change.
- Use it for: Measuring how much work incremental refresh is avoiding.

### `pcg_runtime_retry_policy_max_attempts`
### `pcg_runtime_retry_policy_retry_delay_seconds`

- Type: Gauge
- Meaning: Effective retry policy exposed by runtime and stage.
- Use them for: Debugging whether retries are a behavior issue or simply a
  configuration choice.

### `pcg_runtime_queue_total`
### `pcg_runtime_queue_outstanding`
### `pcg_runtime_queue_pending`
### `pcg_runtime_queue_in_flight`
### `pcg_runtime_queue_retrying`
### `pcg_runtime_queue_succeeded`
### `pcg_runtime_queue_dead_letter`
### `pcg_runtime_queue_failed`
### `pcg_runtime_queue_overdue_claims`
### `pcg_runtime_queue_oldest_outstanding_age_seconds`

- Type: Gauge family
- Meaning: Shared runtime queue depth and age surface.
- Use them for: The first backlog dashboard you open when a runtime feels slow,
  stuck, or retry-heavy.

### `pcg_runtime_stage_items`

- Type: Gauge
- Meaning: Work-item counts by `service_name`, `stage`, and `status`.
- Use it for: Pinpointing whether pressure is concentrated in collector,
  projector, reducer, or replay behavior.

### `pcg_runtime_generation_total`

- Type: Gauge
- Meaning: Generation lifecycle totals by state.
- Use it for: Understanding whether changed scopes are draining into active,
  superseded, or failed generations as expected.

### `pcg_runtime_domain_outstanding`
### `pcg_runtime_domain_retrying`
### `pcg_runtime_domain_dead_letter`
### `pcg_runtime_domain_failed`
### `pcg_runtime_domain_oldest_age_seconds`

- Type: Gauge family
- Meaning: Domain-specific backlog and age.
- Use them for: Answering which platform slice is actually stuck instead of
  treating the whole reducer or runtime as one opaque backlog.

## Data-Plane Throughput And Queueing

These metrics are emitted by the Go telemetry instruments used by the
collector/projector/reducer path.

### `pcg_dp_queue_depth`
### `pcg_dp_queue_oldest_age_seconds`
### `pcg_dp_queue_claim_duration_seconds`

- Type: Gauge, gauge, histogram
- Meaning: Queue depth, oldest pending age, and claim latency for the
  facts-first work queue.
- Use them for: Autoscaling and backlog diagnosis across the data plane.

### `pcg_dp_worker_pool_active`

- Type: Gauge
- Meaning: Active worker count for instrumented worker pools.
- Use it for: Confirming whether configured parallelism is actually in use.

### `pcg_dp_collector_observe_duration_seconds`
### `pcg_dp_repo_snapshot_duration_seconds`
### `pcg_dp_repos_snapshotted_total`
### `pcg_dp_file_parse_duration_seconds`
### `pcg_dp_files_parsed_total`

- Type: Histograms and counters
- Meaning: Repository discovery, snapshot, and parse throughput.
- Use them for: Measuring collector cost and spotting oversized repos or slow
  parse phases.

### `pcg_dp_fact_emit_duration_seconds`
### `pcg_dp_facts_emitted_total`
### `pcg_dp_facts_committed_total`
### `pcg_dp_fact_batches_committed_total`
### `pcg_dp_generation_fact_count`

- Type: Histograms and counters
- Meaning: Fact emission and durable commit volume.
- Use them for: Understanding whether slowdowns happen before queueing or after
  facts are already materialized.

### `pcg_dp_projector_run_duration_seconds`
### `pcg_dp_projector_stage_duration_seconds`
### `pcg_dp_projections_completed_total`

- Type: Histograms and counter
- Meaning: Source-local projector latency and completion volume.
- Use them for: Separating projector latency from reducer latency.

### `pcg_dp_reducer_intents_enqueued_total`
### `pcg_dp_reducer_executions_total`
### `pcg_dp_reducer_run_duration_seconds`
### `pcg_dp_reducer_batch_claim_size`

- Type: Counters, histogram, gauge
- Meaning: Reducer enqueue, execution, latency, and claim-size behavior.
- Use them for: Tuning reducer concurrency and validating that shared follow-up
  is not starving the main reducer path.

## Shared Follow-Up And Acceptance

### `pcg_dp_shared_projection_cycles_total`
### `pcg_dp_shared_projection_stale_intents_total`

- Type: Counters
- Meaning: Shared-projection loop cycles and stale-intent cleanup activity.
- Use them for: Detecting whether follow-up work is running but constantly
  finding stale or superseded intents.

### `pcg_dp_shared_acceptance_lookup_duration_seconds`
### `pcg_dp_shared_acceptance_lookup_errors_total`
### `pcg_dp_shared_acceptance_upsert_duration_seconds`
### `pcg_dp_shared_acceptance_upserts_total`
### `pcg_dp_shared_acceptance_prefetch_size`
### `pcg_dp_shared_acceptance_rows`

- Type: Histograms, counters, gauge, histogram
- Meaning: Lookup and write behavior for shared acceptance state.
- Use them for: Diagnosing slow or error-prone shared follow-up decisions and
  validating batch sizing.

## Storage, Graph, And Cross-Repo Work

### `pcg_dp_postgres_query_duration_seconds`
### `pcg_dp_neo4j_query_duration_seconds`

- Type: Histogram
- Meaning: Storage query latency for Postgres and Neo4j.
- Use them for: Telling whether the bottleneck is the queueing layer or the
  underlying storage round-trips.

### `pcg_dp_neo4j_deadlock_retries_total`

- Type: Counter
- Meaning: Deadlock retries observed on Neo4j write paths.
- Use it for: Detecting contention regressions and verifying deadlock hardening.

### `pcg_dp_neo4j_batch_size`
### `pcg_dp_neo4j_batches_executed_total`

- Type: Histogram and counter
- Meaning: Neo4j batch sizing and batch execution volume.
- Use them for: Tuning write chunking and understanding write amplification.

### `pcg_dp_canonical_writes_total`
### `pcg_dp_canonical_write_duration_seconds`
### `pcg_dp_canonical_atomic_writes_total`
### `pcg_dp_canonical_atomic_fallbacks_total`
### `pcg_dp_canonical_nodes_written_total`
### `pcg_dp_canonical_edges_written_total`
### `pcg_dp_canonical_projection_duration_seconds`
### `pcg_dp_canonical_retract_duration_seconds`
### `pcg_dp_canonical_batch_size`
### `pcg_dp_canonical_phase_duration_seconds`

- Type: Counters, histograms, and gauges
- Meaning: Canonical graph write throughput, latency, fallback behavior, and
  phase-level cost.
- Use them for: Understanding whether graph cost comes from projection, retract,
  batching, or atomic fallback behavior.

### `pcg_dp_cross_repo_resolution_duration_seconds`
### `pcg_dp_cross_repo_evidence_loaded_total`
### `pcg_dp_cross_repo_edges_resolved_total`
### `pcg_dp_evidence_facts_discovered_total`

- Type: Histogram and counters
- Meaning: Cross-repo resolution and evidence-loading work.
- Use them for: Diagnosing relationship-mapping cost and evidence sparsity.

## Capacity And Pipeline Shape

### `pcg_dp_discovery_dirs_skipped_total`
### `pcg_dp_discovery_files_skipped_total`

- Type: Counter
- Meaning: Filesystem entries pruned during discovery.
- Use them for: Verifying ignore policy behavior and explaining why a repo scan
  is cheaper than a raw file count might suggest.

### `pcg_dp_large_repo_classifications_total`
### `pcg_dp_large_repo_semaphore_wait_seconds`

- Type: Counter and histogram
- Meaning: Large-repo classification and concurrency throttling.
- Use them for: Tuning large-repo fairness and explaining collector wait time.

### `pcg_dp_content_rereads_total`
### `pcg_dp_content_reread_skips_total`

- Type: Counter
- Meaning: Content reread behavior in the projection path.
- Use them for: Understanding how often content had to be reloaded instead of
  reused.

### `pcg_dp_pipeline_overlap_seconds`

- Type: Histogram
- Meaning: Overlap between major pipeline phases.
- Use it for: Seeing whether parallelism is helping or just increasing memory
  overlap and contention.

### `pcg_dp_gomemlimit_bytes`

- Type: Gauge
- Meaning: Effective Go memory limit exposed by the runtime.
- Use it for: Correlating concurrency tuning with container memory pressure.

## Recommended Dashboards

### Runtime Health

- `pcg_runtime_health_state`
- `pcg_runtime_queue_outstanding`
- `pcg_runtime_queue_oldest_outstanding_age_seconds`
- `pcg_runtime_stage_items`
- `pcg_runtime_domain_oldest_age_seconds`

### Ingest Throughput

- `pcg_dp_repos_snapshotted_total`
- `pcg_dp_files_parsed_total`
- `pcg_dp_facts_emitted_total`
- `pcg_dp_collector_observe_duration_seconds`
- `pcg_dp_projector_run_duration_seconds`
- `pcg_dp_reducer_run_duration_seconds`

### Shared Follow-Up

- `pcg_dp_shared_projection_cycles_total`
- `pcg_dp_shared_projection_stale_intents_total`
- `pcg_dp_shared_acceptance_lookup_duration_seconds`
- `pcg_dp_shared_acceptance_lookup_errors_total`
- `pcg_dp_shared_acceptance_upsert_duration_seconds`

### Storage Pressure

- `pcg_dp_postgres_query_duration_seconds`
- `pcg_dp_neo4j_query_duration_seconds`
- `pcg_dp_neo4j_deadlock_retries_total`
- `pcg_dp_canonical_write_duration_seconds`
- `pcg_dp_canonical_atomic_fallbacks_total`

If you need exact repository, scope, generation, or work-item context, move
from metrics into [traces](traces.md) and [logs](logs.md). Metrics should tell
you where to look next, not carry the full debugging payload themselves.
