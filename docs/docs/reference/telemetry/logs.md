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

Why it matters:

- provides the breadcrumb trail for repo-level indexing behavior

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

