# Telemetry Logs

Logs are the highest-context signal in PCG.

Use them when you need:

- exact error text
- a breadcrumb trail for one repository, run, or work item
- structured event details that do not belong in metric labels
- a direct bridge from human-readable context into traces

## Canonical Log Shape

PCG writes one JSON document per log line.

Important top-level fields:

- `timestamp`
- `severity_text`
- `message`
- `event_name`
- `service_name`
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

## Why Logs Matter

Metrics tell you that something is wrong.
Traces tell you where the time went.
Logs tell you what actually happened in human terms.

That makes logs the best signal for:

- debugging retries and fallback behavior
- understanding why work items were dead-lettered
- understanding why a repository failed
- explaining queue churn and compatibility behavior
- reconstructing operator actions during incidents

## Important Event Families

### API and MCP

- `http.request.completed`
- `mcp.request.received`
- `mcp.tool.completed`

Why it matters:

- gives request context and completion details that metrics intentionally omit

### Git Collector

- `index.discovery.completed`
- `index.parse.started`
- `index.parse.progress`
- `index.parse.slow_file`
- `index.repository.started`
- `index.repository.commit_wait.completed`
- `index.repository.commit.started`
- `index.repository.completed`
- `facts.snapshot.emitted`
- `facts.inline_projection.leased`
- `facts.inline_projection.lease_missed`
- `facts.inline_projection.failed`
- `facts.inline_projection.completed`

Why it matters:

- provides the breadcrumb trail for repo-level indexing behavior
- shows where the Git collector handed work to the facts-first pipeline

### Graph persistence

- `graph.batch.commit.started`
- `graph.batch.commit.chunk_retry`
- `graph.batch.commit.file_failed`
- `graph.batch.entity.flush`
- `graph.batch.chunk.started`
- `graph.batch.chunk.completed`

Why it matters:

- best source for fallback and chunk-level persistence behavior

### Content persistence

- `content.dual_write.failed`
- `content.dual_write_batch.failed`

Why it matters:

- explains silent content-store misses that metrics alone cannot describe

### Resolution Engine

- `resolution.work_item.projected`
- `resolution.work_item.completed`
- `resolution.work_item.failed`
- `resolution.work_item.dead_lettered`
- `resolution.decision.recorded`
- `resolution.stage.failed`

Why it matters:

- explains whether the failure happened during fact load, relationship projection, workload/platform materialization, or final work-item completion
- gives on-call responders the exact `work_item_id`, `source_run_id`, and error class needed to replay or investigate
- records explainable confidence decisions so operators can inspect why a relationship, workload, or platform edge was produced

### Index status and refinalize

- `http.request.completed`
- `index.finalization.started`
- `index.finalization.partial_start`
- `index.finalization.stage.completed`
- `index.finalization.completed`
- `index.finalization.deferred`
- `admin.refinalize.started`
- `admin.refinalize.stage`
- `admin.refinalize.completed`
- `admin.refinalize.failed`
- `admin.refinalize.coverage_repair.started`
- `admin.refinalize.coverage_repair.completed`
- `admin.refinalize.coverage_repair.failed`

Why it matters:

- `GET /api/v0/index-status` and `GET /api/v0/index-runs/{run_id}` are read
  paths, so their breadcrumbs usually come from the HTTP request log plus the
  underlying finalization events
- graph-safe admin refinalize should emit the admin.refinalize family only
- file-dependent bridge stages remain CLI-only, so they should show up in the
  legacy bridge/finalization logs instead of the admin.refinalize family

### Admin and operator workflow

- `admin.facts.replayed`
- `admin.facts.work_items.listed`
- `admin.facts.decisions.listed`
- `admin.facts.dead_lettered`
- `admin.facts.backfill.requested`
- `admin.facts.replay_events.listed`

Why it matters:

- records deliberate replay actions against dead-lettered fact work items so incident timelines stay auditable
- provides a direct breadcrumb when retry pressure drops because an operator manually replayed failed work
- makes queue inspection, dead-letter overrides, and backfill requests visible in the same incident timeline as runtime failures

## What Belongs In `extra_keys`

Good fields for `extra_keys`:

- `run_id`
- `repo_id`
- `repo_name`
- `repo_path`
- `phase`
- `status`
- `duration_seconds`
- `rows`
- `batch_type`
- `backend`
- `file_path`
- `worker_id`
- `work_item_id`
- `source_run_id`
- `attempt_count`
- `error_class`
- `replayed_count`

These are high-value because they are useful for incident filtering but too high-cardinality for metric labels.

## How To Leverage Logs

### During an incident

1. Start from the alerting metric.
2. Filter logs by `service_name`, `component`, and the likely time window.
3. Narrow with `run_id`, `repo_path`, or `work_item_id`.
4. Jump into the matching trace with `trace_id`.

### During performance tuning

Use logs to validate what the metrics imply:

- slow parse files
- commit chunk retries
- per-worker behavior
- fallback paths

### During autoscaling work

Use logs to confirm whether worker saturation is real or whether the queue/database path is the true bottleneck.

## Relationship To Existing Logging Standard

This page is the operator-facing guide.

For the full logging envelope and platform rules, see the existing [Logging Standard](../logging.md).
