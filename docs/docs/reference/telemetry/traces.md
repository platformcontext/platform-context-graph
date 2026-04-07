# Telemetry Traces

Traces answer one question better than any other signal:

**Where did the time go for this specific request, run, repository, or work item?**

## Trace Strategy

PCG uses OTEL spans for:

- request boundaries
- indexing and parse boundaries
- facts-first persistence and queue boundaries
- Resolution Engine work-item processing
- graph and content persistence
- Neo4j query timing

Use metrics to detect a problem first, then traces to explain it.

## Key Spans By Runtime

### API and MCP

- `pcg.http.*` request spans from the API runtime
- `pcg.query.*` spans around shared query operations
- `pcg.mcp.*` request and tool spans in the MCP runtime

Investigation-specific query spans continue to use the shared query family:

- `pcg.query.investigate_service`

Why it matters:

- shows slow requests end-to-end
- exposes whether latency came from transport, graph query, or content retrieval
- makes service-investigation widening visible without requiring prompt-expert logs

### Git Collector

- `pcg.index.run`
- `pcg.index.repository`
- `pcg.index.repository.queue_wait`
- `pcg.index.repository.parse`
- `pcg.index.repository.commit`
- `pcg.index.parse_repository`
- `pcg.index.prescan_repository`
- `pcg.facts.emit_snapshot`
- `pcg.facts.inline_projection`

Why it matters:

- separates parse time, queue wait, fact emission time, and inline projection time
- shows whether the collector is CPU-bound, queue-bound, or persistence-bound

### Fact Store and Queue

- `pcg.fact_store.upsert_fact_run`
- `pcg.fact_store.upsert_facts`
- `pcg.fact_store.list_facts`
- `pcg.fact_queue.enqueue_work_item`
- `pcg.fact_queue.claim_work_item`
- `pcg.fact_queue.lease_work_item`
- `pcg.fact_queue.fail_work_item`
- `pcg.fact_queue.complete_work_item`
- `pcg.fact_queue.replay_failed_work_items`
- `pcg.fact_queue.dead_letter_work_items`
- `pcg.fact_queue.request_backfill`
- `pcg.fact_queue.list_replay_events`
- `pcg.fact_queue.list_queue_snapshot`

Why it matters:

- shows the actual SQL-boundary cost of the new facts-first architecture
- gives direct proof when Postgres becomes the bottleneck
- includes the operator replay, dead-letter, audit, and backfill request paths for recovery workflows

### Resolution Engine

- `pcg.resolution.iteration`
- `pcg.resolution.project_work_item`
- `pcg.resolution.load_facts`
- `pcg.resolution.project_facts`
- `pcg.resolution.project_file_batch`
- `pcg.resolution.project_relationships`
- `pcg.resolution.project_workloads`
- `pcg.resolution.project_platforms`

Why it matters:

- shows whether time is lost in claim, fact loading, relationship projection, workload materialization, or platform inference
- makes large-repo file projection visible as its own span instead of blending it into `project_facts`

### Graph and Content Persistence

- `pcg.graph.commit_chunk`
- `pcg.content.dual_write`
- `pcg.content.dual_write_batch`
- `pcg.content.postgres.upsert_file_batch`
- `pcg.calls.known_name_scan`
- `pcg.inheritance.flush_batch`
- `pcg.neo4j.query`

Why it matters:

- lets you see where write latency is really being spent
- useful when graph or content persistence becomes the tail-latency driver
- shows whether large-repo slowdowns are now in content batch writes, CALLS prefilter scans, or inheritance flushing

## Important Span Attributes

These attributes are especially useful for narrowing traces:

- `pcg.component`
- `pcg.transport`
- `pcg.request_id`
- `pcg.correlation_id`
- `pcg.investigation.service_name`
- `pcg.investigation.intent`
- `pcg.investigation.environment`
- `pcg.investigation.deployment_mode`
- `pcg.investigation.repositories_considered_count`
- `pcg.investigation.repositories_with_evidence_count`
- `pcg.investigation.evidence_families_found_count`
- `pcg.investigation.missing_evidence_families_count`
- `pcg.index.run_id`
- `pcg.index.repo_path`
- `pcg.repository_id`
- `pcg.facts.source_run_id`
- `pcg.facts.source_snapshot_id`
- `pcg.facts.work_item_id`
- `pcg.queue.attempt_count`
- `db.system`
- `db.operation`

## Incident Recipes

### A queued backlog is rising

1. Start with `pcg_fact_queue_oldest_age_seconds`.
2. Open traces for `pcg.fact_queue.claim_work_item` and `pcg.resolution.project_work_item`.
3. Decide whether the delay is in queue claim, fact loading, or stage projection.

### A single repository got much slower

1. Start with `pcg_index_repository_duration_seconds`.
2. Open the `pcg.index.repository` trace for the slow repo.
3. Compare parse span, fact emission span, `pcg.resolution.project_file_batch`, and `pcg.resolution.project_relationships`.

### Graph writes are slow

1. Start with `pcg_graph_write_batch_duration_seconds`.
2. Open the related `pcg.graph.commit_chunk` trace.
3. Inspect nested `pcg.neo4j.query` spans to see which Cypher operation dominates.

### A giant repo is threatening memory or throughput

1. Start with `pcg_resolution_file_projection_batch_duration_seconds`, `pcg_content_file_batch_upsert_duration_seconds`, and `pcg_call_prep_calls_capped_total`.
2. Open traces for `pcg.resolution.project_file_batch`, `pcg.content.postgres.upsert_file_batch`, `pcg.calls.known_name_scan`, and `pcg.inheritance.flush_batch`.
3. Decide whether the hot path is still file/content IO or has moved into relationship preparation and flushes.

### A service investigation feels too shallow

1. Open the `pcg.query.investigate_service` trace for the affected request.
2. Check `pcg.investigation.deployment_mode`,
   `pcg.investigation.repositories_considered_count`, and
   `pcg.investigation.missing_evidence_families_count`.
3. Use the trace attributes to decide whether the issue is sparse evidence,
   repo-widening failure, or downstream query latency.

## Best Practices

- Use metrics to choose the right trace first.
- Filter by `service.name` to separate API, ingester, and resolution-engine behavior.
- Use `request_id`, `correlation_id`, `run_id`, and `work_item_id` to jump from logs into traces quickly.
