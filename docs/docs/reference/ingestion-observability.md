# Ingestion Observability

For the broader service-wide telemetry references, see:

- [Telemetry Overview](telemetry/index.md)
- [Telemetry Metrics](telemetry/metrics.md)
- [Telemetry Traces](telemetry/traces.md)
- [Telemetry Logs](telemetry/logs.md)

This page is the operator-facing map for indexing and repository-ingestion
telemetry. Use it when you need to answer "is the run healthy?", "where is it
stuck?", or "did the queue/backpressure model behave the way we expected?".

## Runtime Model

```mermaid
flowchart LR
  A["Discovery and run state"] --> B["Parse workers"]
  B --> C["Bounded snapshot queue"]
  C --> D["Serialized commit"]
  D --> E["Finalization"]
```

The main process owns the control plane:

- run-state checkpoints
- queue creation and backpressure
- commit orchestration
- finalization
- coverage publication
- telemetry aggregation

Worker processes own parse work:

- parser initialization
- repo pre-scan and file parsing
- returning serializable repository snapshots

The queue between parse and commit is bounded by `PCG_INDEX_QUEUE_DEPTH`.
Worker fanout is controlled by `PCG_PARSE_WORKERS`. Per-repo file concurrency
can still be tuned with `PCG_REPO_FILE_PARSE_CONCURRENCY`. Set
`PCG_REPO_FILE_PARSE_MULTIPROCESS=true` when you want file parsing within a
repository snapshot to use the process-pool path instead of the threaded path.
`PCG_MULTIPROCESS_START_METHOD` defaults to `spawn`; keep that unless you have
validated a different start method on the exact runtime you deploy.

## Correlation Keys

Use these fields to move between Grafana, Loki, and traces:

- `run_id`
- `repo_id`
- `repo_name`
- `repo_path`
- `phase`
- `status`
- `component`
- `mode`
- `source`
- `trace_id`
- `span_id`

## Status Surfaces

Use the operator surface that matches the question you are trying to answer:

- `pcg index-status` is the fastest local or remote checkpointed completeness
  signal.
- `GET /api/v0/status/index` is the normalized deployed completeness view
  exposed by the public Go API service.
- `GET /api/v0/index-status` is the compatibility alias for the same payload.
- `GET /admin/status` is the live runtime-health and backlog surface for Go
  runtimes and other services that mount the shared runtime admin contract.

Keep the distinction explicit:

- `/health`, `/healthz`, and `/readyz` answer process health and readiness, not
  whether a scope, repository, or generation has finished indexing.
- `index-status` answers checkpointed run completeness, not whether a runtime
  is currently healthy.
- run-scoped completeness routes are intentionally not part of the shipped
  public contract on this branch; use repository coverage plus checkpoint logs
  when you need narrower evidence today.
- `POST /admin/refinalize` and `POST /admin/replay` are Go-owned repair
  surfaces. Use them for controlled recovery and backlog repair, not as part of
  the normal indexing path.

## Spans

| Span name | Where it appears | Why it matters |
| --- | --- | --- |
| `pcg.index.run` | whole indexing run | top-level run duration and status |
| `pcg.index.repository` | one repository lifecycle | parse/commit timing per repository |
| `pcg.index.repository.queue_wait` | one repository lifecycle | how long a repo waited for a parse slot |
| `pcg.index.repository.parse` | one repository lifecycle | time spent building the repository snapshot |
| `pcg.index.repository.commit_wait` | one repository lifecycle | how long a parsed snapshot waited for commit |
| `pcg.index.repository.commit` | one repository lifecycle | time spent committing one repository snapshot |
| `pcg.index.parse_repository` | repository parse | parse-only timing and strategy |
| `pcg.index.prescan_repository` | repository pre-scan | import-map discovery cost |
| `pcg.index.finalize` | run finalization | post-parse relationship work |
| `pcg.index.finalize.stage` | one finalization sub-step | latency of each named finalization stage |
| `pcg.index.checkpoint.save_run_state` | checkpoint persistence | run-state durability timing |
| `pcg.index.checkpoint.save_snapshot_metadata` | staged snapshot metadata | snapshot write health |
| `pcg.index.checkpoint.save_snapshot_file_data` | staged snapshot file data | snapshot payload durability |
| `pcg.index.checkpoint.load_snapshot_metadata` | resume path | checkpoint resume health |
| `pcg.index.checkpoint.load_snapshot_file_data` | resume path | checkpoint resume health |
| `pcg.indexing.publish_repository_coverage` | coverage publication | gap detection between discovery, graph, and content |

Useful span attributes:

- `pcg.index.run_id`
- `pcg.index.repo_path`
- `pcg.index.repo_count`
- `pcg.index.file_count`
- `pcg.index.resume`
- `pcg.index.mode`
- `pcg.index.source`
- `pcg.index.file_parse_strategy`

The `pcg.index.finalize*` spans now describe Go-owned repair and reconciliation
work, not an active Python bridge. Treat them as repair-path evidence, not as
the canonical telemetry family for new architecture work. New projector or
reducer behavior should emit queue, projector, or reducer spans instead of
extending the finalization family.

## Metrics

| Metric | Labels | What it answers |
| --- | --- | --- |
| `pcg_index_active_runs` | `component`, `mode`, `source` | how many indexing runs are active right now |
| `pcg_index_active_repositories` | `component`, `mode`, `source` | how many repositories are currently in flight |
| `pcg_index_checkpoint_pending_repositories` | `component`, `mode`, `source` | how many repositories are still waiting on checkpoint completion |
| `pcg_index_runs_total` | `component`, `mode`, `source`, `status`, `resume`, `finalization_status` | how many runs started, resumed, failed, or completed |
| `pcg_index_run_duration_seconds` | `component`, `mode`, `source`, `status`, `resume`, `finalization_status` | end-to-end run latency |
| `pcg_index_repositories_total` | `component`, `phase`, `mode`, `source` | repository lifecycle counts by phase |
| `pcg_index_repository_duration_seconds` | `component`, `mode`, `source`, `status` | per-repository latency and failure timing |
| `pcg_index_stage_duration_seconds` | `component`, `mode`, `source`, `stage`, `parse_strategy`, `parse_workers` | where queueing, parsing, committing, or finalization time is going |
| `pcg_index_checkpoints_total` | `component`, `mode`, `source`, `operation`, `status` | checkpoint save and resume activity |
| `pcg_index_snapshot_queue_depth` | `component`, `mode`, `source`, `parse_strategy`, `parse_workers` | how much parsed work is waiting to commit |
| `pcg_index_parse_tasks_active` | `component`, `mode`, `source`, `parse_strategy`, `parse_workers` | how many file parse tasks are currently in flight |
| `pcg_hidden_dirs_skipped_total` | `component`, `kind` | what hidden directories were filtered out |
| `pcg_index_lock_contention_skips_total` | `component`, `mode`, `source` | whether a run was skipped because another worker held the lock |
| `pcg_graph_write_batch_duration_seconds` | `pcg.component`, `pcg.graph.batch_type`, `pcg.graph.label` | graph write latency by batch type |
| `pcg_graph_write_batch_rows` | `pcg.component`, `pcg.graph.batch_type`, `pcg.graph.label` | batch size distribution |

Adjacent signals that are useful when ingest and content storage interact:

- `pcg_content_provider_requests_total`
- `pcg_content_provider_duration_seconds`
- `pcg_content_workspace_fallback_total`

Those content metrics use labels such as `pcg.component`,
`pcg.content.operation`, `pcg.content.backend`, `pcg.content.success`, and
`pcg.content.hit`.

## Log Events

The stable ingestion log families are:

- `index.discovery.completed`
- `index.path.started`
- `index.path.failed`
- `index.parse.started`
- `index.parse.dispatch.configured`
- `index.parse.worker_handoff`
- `index.parse.progress`
- `index.parse.slow_file`
- `index.parse.slowest_files`
- `index.parse.completed`
- `index.repository.started`
- `index.repository.queue_wait.completed`
- `index.repository.parse.started`
- `index.repository.parse.completed`
- `index.repository.commit_wait.completed`
- `index.repository.commit.started`
- `index.repository.commit.completed`
- `index.repository.completed`
- `index.finalization.started`
- `index.finalization.stage.completed`
- `index.finalization.completed`
- `index.finalization.deferred`
- `index.finalization.failed`
- `index.scip.started`
- `index.scip.unavailable`
- `index.scip.unsupported`
- `indexing.repository_coverage.published`

During rollout you may also see `index.parse.multiprocess_skeleton.enabled`.
Treat that as compatibility noise, not a dashboard baseline.

Treat `index.finalization.*` the same way for new architecture work: these
events remain important for repair visibility, but they are not the target
event family for future collector, projector, or reducer logic.

When an operator needs to answer "is the service alive?" versus "did the data
plane finish the work?", pair the log family with the matching status surface:

- health or readiness questions: runtime probe endpoints and runtime logs
- completeness questions: `index-status`, repository coverage, and checkpoint
  logs
- repair-path questions: finalization spans, `index.finalization.*`, and
  `pcg finalize` or `/admin/refinalize` output

## Dashboard Questions

| Question | Best signals |
| --- | --- |
| Is the run alive and moving? | `pcg_index_active_runs`, `pcg_index_active_repositories`, `pcg_index_checkpoint_pending_repositories`, `index.parse.progress` |
| Is parse throughput the bottleneck? | `pcg_index_repository_duration_seconds`, `index.parse.slow_file`, `index.parse.slowest_files`, `pcg.index.parse_repository` |
| Is commit or finalization slowing us down? | `pcg.index.repository`, `pcg.index.finalize`, `index.finalization.*`, finalization stage timings |
| Are checkpoints keeping up with parse work? | `pcg_index_checkpoints_total`, `pcg_index_checkpoint_pending_repositories`, `indexing.repository_coverage.published` |
| Did a repository fail or get skipped? | `index.repository.completed` with failure status, `index.path.failed`, `index.finalization.failed`, lock-contention skips |

## Correlation Recipe

1. Start from a Grafana panel or alert and filter by `component`, `mode`, and
   `source`.
2. Narrow to a `run_id` or `repo_id`.
3. Use `trace_id` to jump from logs into the matching trace.
4. Use `repo_path` and `phase` when you need a human-readable breadcrumb trail.
