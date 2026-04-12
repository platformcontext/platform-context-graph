# Telemetry Overview

PlatformContextGraph uses three signal types:

- **Metrics** for rate, latency, backlog, concurrency, and capacity trends
- **Traces** for request and pipeline timing across service boundaries
- **Logs** for high-context event breadcrumbs and incident forensics

Use this page to choose where to look first.

Operator/admin status is part of the telemetry contract, not a separate debug
path. If a service exposes `/admin/status`, treat that report as the fastest
way to understand what stage is running, how much work is queued, and whether
the reported state is live or inferred.

## Start Here

| If you are debugging | Start with | Then check |
| --- | --- | --- |
| API is slow or erroring | API metrics | API traces and logs |
| backlog is growing | queue depth and queue age metrics | resolution-engine traces and queue logs |
| shared follow-up looks stuck | shared-projection backlog metrics | resolution-engine traces and shared-projection logs |
| one repository is slow | ingester metrics | ingester traces and resolution-engine stage timings |
| graph writes are slow | resolution metrics | Neo4j traces and graph persistence logs |
| content reads are missing or slow | API metrics and content metrics | content traces and logs |
| replay or dead-letter behavior looks wrong | recovery metrics | recovery traces and admin/replay logs |

## Runtime And Control-Plane Flow

```mermaid
flowchart LR
  A["Ingester"] --> B["Postgres fact store"]
  B --> C["Fact work queue"]
  C --> D["Resolution Engine"]
  D --> E["Neo4j graph"]
  D --> F["Postgres content store"]
  D --> G["Projection decisions"]
  C --> H["Failure and replay state"]
  I["API / MCP"] --> E
  I --> F
  J["Admin API / CLI"] --> G
  J --> H
  J --> I
```

## How To Use The Signals

- Start with **metrics** when you need to detect regression, saturation, or
  backlog growth.
- Move to **traces** when you need to understand where time went across a
  request or projection.
- Use **logs** when you need exact repository, run, or work-item context.
- Use the shared admin/status report when you want a quick read on stage,
  backlog, live-versus-inferred state, and failure classification.

## Incremental Refresh And Reconciliation Signals

The rewrite is moving toward incremental refresh and reconciliation, not full
re-indexing as the normal freshness model.

Watch these signals together:

- scope and generation status for what changed
- work-queue depth and age for what still needs to be reconciled
- projection decisions for what has been accepted or deferred
- retry and dead-letter state for what needs operator attention

If a repository, scope, or collector appears stale, start with the admin/status
surface and queue/generation metrics before assuming a full rebuild is needed.

For shared-write debugging specifically:

- Start with `pcg_shared_projection_pending_intents` and
  `pcg_shared_projection_oldest_pending_age_seconds` to see whether
  authoritative platform or dependency follow-up is actually building up.
- Use `pcg_fact_queue_depth` and `pcg_fact_queue_oldest_age_seconds` alongside
  the shared-projection gauges rather than instead of them. Fact queue growth
  and shared follow-up growth answer different questions.
- Pivot to traces when backlog exists but is not draining. Pivot to logs when
  you need the exact repository, run, generation, or partition owner involved.
- The runtime status surface now carries `shared_projection_tuning` whenever
  shared backlog is present, so operators can see the current recommended
  partition/batch setting from `get_ingester_status` before opening the
  separate admin tuning report.

## By Runtime

### API

- Metrics answer request rate, latency, and error-rate questions.
- Traces show request and query timing.
- Logs carry correlation fields and failure details.

### Ingester

- Metrics answer repo queue wait, parse throughput, fact emission timing, and
  workspace pressure.
- Traces show parse, fact emission, and inline projection timing.
- Logs explain discovery choices, slow files, and per-repo progress.

### Facts Layer

- Metrics answer fact-store latency, queue backlog depth, queue age, retry
  churn, dead-letter pressure, and connection-pool saturation.
- Traces show individual fact-store and fact-queue operations.
- Logs capture snapshot emission, inline lease behavior, replay, and work-item
  lifecycle breadcrumbs.

### Resolution Engine

- Metrics answer claim latency, worker activity, stage duration, stage output
  volume, stage failures, dead-letter pressure, and shared authoritative
  follow-up backlog.
- Traces show one projection attempt from claim to graph write.
- Logs capture work-item completion, retry, dead-letter, and per-stage failure
  context.

### Admin / CLI Status

- The admin/status report answers stage, backlog, health, and live-versus-
  inferred questions in one place.
- It should mirror the service runtime shape so operators do not need a
  different mental model for collector, projector, reducer, or future Go
  services.
- Use the report before restarting a service or forcing a broader re-index.

Shared-write-specific gauges:

- `pcg_shared_projection_pending_intents` reports how many uncompleted shared
  projection intents exist per `pcg.projection_domain`.
- `pcg_shared_projection_oldest_pending_age_seconds` reports the age of the
  oldest uncompleted shared projection intent per `pcg.projection_domain`.

These gauges are intentionally domain-scoped and do not carry repository
identity. Use traces and logs when you need repository-level detail.

## Rollout Validation For Shared-Write Changes

When validating shared-write runtime changes in staging or production:

1. Start with `pcg_fact_queue_depth`, `pcg_fact_queue_oldest_age_seconds`,
   `pcg_shared_projection_pending_intents`, and
   `pcg_shared_projection_oldest_pending_age_seconds`.
2. Confirm backlog trends are flat-to-down, not simply that pods are up.
3. If shared backlog remains non-zero, inspect traces for the affected
   projection domain before assuming the fact queue is the bottleneck.
4. Use logs last to extract exact repository, source run, generation, or lease
   owner context for the stuck or slow path.

## Tuning Guidance For Shared-Write Backlog

The deterministic shared-write load harness currently shows this balanced
dependency scenario:

| Partition count | Batch limit | Drain rounds | Mean processed per round |
| --- | --- | --- | --- |
| 1 | 1 | 16 | 2.0 |
| 2 | 1 | 8 | 4.0 |
| 4 | 1 | 5 | 6.4 |
| 4 | 2 | 2 | 16.0 |

Interpretation:

- Increasing partition count produces the first major drain-round reduction by
  spreading stable lock domains across more workers.
- Once partitioning is already helping, a modest batch increase can remove the
  remaining tail rounds quickly.
- Batch increases should come after partition increases, not before them, so we
  avoid hiding a partitioning bottleneck behind larger per-round writes.

Recommended staging order:

1. Increase partition count and watch
   `pcg_shared_projection_pending_intents` plus
   `pcg_shared_projection_oldest_pending_age_seconds`.
2. Confirm fact queue metrics stay flat-to-down at the same time:
   `pcg_fact_queue_depth` and `pcg_fact_queue_oldest_age_seconds`.
3. Only then try a modest batch-limit increase if backlog still drains in too
   many rounds after partitioning is healthy.

If partition count goes up but oldest pending age still rises, traces should be
the next stop before turning batch size further.

## Prometheus And ServiceMonitor

- In Docker Compose, validate runtime metrics by curling the direct `/metrics`
  endpoints.
- In Kubernetes, Helm can expose dedicated metrics ports and render
  `ServiceMonitor` resources for the API, ingester, and resolution-engine.
- Bootstrap indexing is a local or operator-run one-shot activity, not a
  steady-state `ServiceMonitor` target in the public chart.
- Incremental refresh and reconciliation should be observed through queue age,
  generation status, and the admin/status surface rather than through a
  platform-wide re-index trigger.

## Where To Go Next

- [Metrics](metrics.md) for exact metric names and how to use them
- [Traces](traces.md) for span names and latency debugging
- [Logs](logs.md) for event breadcrumbs and incident forensics
- [Baseline Performance](../baseline-performance.md) for large-run tuning
