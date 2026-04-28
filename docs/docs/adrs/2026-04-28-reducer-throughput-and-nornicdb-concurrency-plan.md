# ADR: Reducer Throughput And NornicDB Concurrency Plan

**Date:** 2026-04-28
**Status:** Proposed
**Related:**

- `2026-04-18-reducer-full-convergence-optimization.md`
- `2026-04-22-nornicdb-graph-backend-candidate.md`
- `docs/docs/reference/nornicdb-tuning.md`
- `docs/docs/reference/telemetry/index.md`

## Decision

Treat reducer throughput as an architecture track, not as another round of
timeout and batch-size tuning.

The next phase will:

1. preserve graph correctness gates,
2. measure reducer queue wait, actual work time, and conflict blocking,
3. remove false serialization from reducer claim/routing policy,
4. make shared projection lanes partitionable by the real conflict unit,
5. tune the highest-cost Cypher shapes and NornicDB lookup paths from evidence,
6. only then raise worker or pod concurrency as a default.

This ADR does not accept "run fewer workers" as the end state. Sequential or
low-worker settings remain diagnostic tools for isolating correctness bugs, not
the desired production architecture.

## Context

The 2026-04-28 remote full-corpus proof ran against the 896-repository corpus
on a 16-vCPU, 128 GiB VM with Docker. The run completed without failed or
dead-lettered reducer work, but the wall clock was unacceptable:

- `896` repositories collected in about `6m30s`.
- Source-local projection finished by about `22m26s`.
- The reducer queue drained in about `7h43m40s`.
- Persisted queue state ended healthy: all `9182` work items succeeded.
- Only `14` retries were recorded, so this was not primarily a retry storm.

The strongest measured signal is that wall time was dominated by reducer queue
wait behind a small number of expensive graph-write domains:

| Domain | Items | Domain wall | Sum actual work | P95 queue wait |
| --- | ---: | ---: | ---: | ---: |
| `source_local` | 896 | `22m26s` | `44m30s` | `25.1s` |
| `semantic_entity_materialization` | 372 | `7h39m58s` | `49h12m48s` | `5h03m42s` |
| `workload_materialization` | 2538 | `7h16m24s` | `3h36m11s` | `6h18m52s` |
| `sql_relationship_materialization` | 896 | `7h42m36s` | `1h09m18s` | `4h19m12s` |
| `deployment_mapping` | 896 | `5h50m04s` | `31m58s` | `4h10m35s` |
| `code_call_materialization` | 896 | `5h46m41s` | `1m43s` | `4h01m43s` |

The top semantic reducers were heavily skewed. One repository took almost four
hours of semantic work by itself, while other domains showed low actual work
but multi-hour queue wait. That means most of the corpus was not slow because
every item was expensive; it was slow because the queue and graph-write shape
let a few hot items dominate the tail.

## Current Flow

The relevant runtime path is:

```text
ingester
  -> commits facts to Postgres
  -> enqueues source-local projector work

projector
  -> claims scope/generation work with leases
  -> builds source-local canonical graph/content projection
  -> writes canonical graph and content store
  -> enqueues reducer intents

reducer
  -> claims fact_work_items with FOR UPDATE SKIP LOCKED
  -> executes domain handlers
  -> writes graph/content/readiness side effects
  -> heartbeats long work
  -> acks, retries, or fails work

shared projection runners
  -> process code calls, repo dependency, shared edges, and repair lanes
  -> gate graph edges behind semantic-node readiness where required
```

Correctness constraints that must remain true:

- semantic nodes must exist before semantic edges depend on them,
- same-scope generations must not overlap destructive graph rewrite phases,
- repo-wide retracts must remain exclusive with writes that depend on the same
  repo generation,
- retries must remain idempotent,
- failed or stale claims must not ack work they no longer own,
- graph/API truth must match persisted fact intent after the run completes.

## Findings

### 1. The bottleneck is not collection alone

Collection and source-local work are significant, but they do not explain a
`7h43m` run. Source-local finished in about `22m26s`; the dominant tail was the
reducer and shared projection work that followed.

### 2. Queue wait hides the true hot path

Several domains had small summed work but multi-hour wall time. That points to
claim ordering, conflict routing, or shared worker lane serialization. A fast
domain waiting four hours is evidence of false or overly broad serialization,
not evidence that the fast domain needs tuning.

### 3. Semantic entity graph writes are the largest measured cost

`semantic_entity_materialization` accumulated about `49h12m` of worker time.
This is the first domain that needs query-shape and backend-path analysis. The
slowest repos were not ordered purely by entity count, so row volume alone is
not the full explanation.

### 4. Existing conflict domains are safe but coarse

The current reducer has useful fences, including row leases, generation gates,
and conflict-key routing. The problem is that several conflict keys are broader
than the actual correctness unit. That protects truth, but it also serializes
work that could run concurrently.

### 5. NornicDB should not be treated as a black box

NornicDB can execute concurrent transactions, but write throughput still
depends on exact Cypher shape, lookup indexes, relationship-existence probes,
MVCC validation, Badger commit ordering, and cache/index contention. Raising
workers without understanding these paths can amplify contention instead of
improving throughput.

### 6. Some PCG Cypher shapes are likely too broad for NornicDB

The highest-risk shapes are:

- multi-label semantic edge anchors,
- repo-wide retracts that filter by `repo_id` without a strong label/index
  anchor,
- workload dependency reads with `OR` predicates across source and target,
- shared-edge retractions that scan broad label families,
- relationship `MERGE` paths that repeatedly probe existing edges.

Neo4j may hide some of this with planner behavior and mature indexes. NornicDB
is forcing PCG to make those assumptions explicit, which is good engineering as
long as we keep the fixes behind backend-safe seams.

## Plan

### Phase 0: Baseline And Guardrails

Status: `in progress`

- Record the full-corpus baseline in this ADR.
- Keep the remote run artifacts and queue SQL used for timing analysis.
- Do not run the full corpus as the first proof for each change.
- Use this proof ladder instead:
  1. one large failing or slow repository,
  2. one small repository,
  3. one mixed 20-25 repository corpus,
  4. one 100 repository corpus,
  5. the full 896 repository corpus.

Exit criteria:

- every proof reports wall clock, queue state, failed/dead-letter counts, and
  top slow domains,
- graph/API truth checks remain green for the changed domain.

### Phase 1: Reducer Observability

Status: `in progress`

Add operator-visible reducer telemetry before changing scheduling semantics:

- work item queue wait versus actual handler duration,
- blocked-by-conflict counts and durations,
- conflict domain and conflict key in structured logs or metrics,
- eligible-but-not-claimed counts where the queue skips work,
- per-domain p50/p95/max handler duration,
- top N slow work items by repo and domain in status or run summary,
- shared projection partition wait and processing duration.

This phase answers: "Are workers idle because there is no eligible work, because
conflict keys are too broad, or because the graph backend is slow?"

### Phase 2: Conflict-Domain Matrix

Status: `planned`

Create an explicit matrix for each reducer domain:

| Domain | Reads | Writes | True conflict unit | Current conflict unit |
| --- | --- | --- | --- | --- |
| `semantic_entity_materialization` | content entities, facts | semantic nodes | repo generation + label/write family | to verify |
| `code_call_materialization` | semantic nodes, call facts | `CALLS` edges | acceptance unit or repo edge family | to verify |
| `sql_relationship_materialization` | SQL facts, semantic nodes | SQL edges | repo + SQL edge family | to verify |
| `workload_materialization` | resolved relationships, workload facts | workload instances | deployment/service scope | to verify |
| `deployment_mapping` | relationship evidence | resolved relationships | deployment repo generation | to verify |

Then narrow only the conflict keys that are provably broader than the real
write/read dependency.

Required edge cases:

- stale generation followed by current generation,
- retry after partial graph write,
- same repo with two queued generations,
- two repos with identical entity names,
- repo-wide retract concurrent with edge upsert,
- slow worker lease expiry and reclaim.

### Phase 3: Shared Runner Partitioning

Status: `planned`

The shared projection runners must stop behaving like global lanes when the
data model allows narrower ownership.

Planned changes:

- give each reducer process a unique lease owner before multi-pod scaling,
- partition code-call projection by acceptance unit or source repo,
- partition repo dependency projection by repo pair or repo scope,
- preserve repo-wide retract exclusivity,
- keep semantic-node-readiness gates intact,
- add ack/fail/heartbeat fencing checks before increasing reducer pods.

This phase is complete only when multiple workers can drain independent graph
families without producing duplicate edges, missing edges, or stale-generation
acks.

### Phase 4: Cypher And Index Hot-Path Work

Status: `planned`

Use `cypher-query-rigor` rules: understand the data distribution and the graph
shape before rewriting queries.

First target: `sql_relationship_materialization`.

Why first:

- it is slow enough to matter,
- its label families are known,
- it is less semantically broad than code-call projection,
- it exercises the same multi-label anchor problem likely affecting other
  semantic edge domains.

Candidate work:

- add NornicDB lookup indexes for hot `repo_id` anchors where query evidence
  proves scans,
- split multi-label source/target anchors into concrete label-specific
  statements,
- replace broad `OR` workload dependency reads with indexed outgoing and
  incoming queries,
- split repo-wide retracts by label family when that improves anchor quality,
- add static tests that reject NornicDB query shapes known to force scans.

Proof must compare current and proposed Cypher on seeded data before the full
corpus run.

### Phase 5: NornicDB Backend Collaboration

Status: `planned`

Continue upstream-first work when PCG exposes a true NornicDB limitation.

Candidate backend improvements:

- validate and promote the direct edge-between lookup index work,
- add observability for index hit/miss, edge-existence probe fanout, commit
  latency, MVCC validation time, and conflict reason,
- benchmark PCG's exact `UNWIND/MERGE` write shapes at `1/2/4/8/16` workers,
- evaluate bulk upsert APIs only after query-shape fixes prove insufficient,
- avoid PCG-side workarounds when a small upstream backend fix is the correct
  long-term answer.

### Phase 6: Controlled Concurrency Increase

Status: `planned`

After Phases 1-4 expose the true safe overlap, test:

- `PCG_REDUCER_WORKERS=8`,
- `PCG_REDUCER_WORKERS=16`,
- batch claim size equal to worker count,
- shared projection workers `8-16`,
- shared projection partitions `16-32`,
- multiple reducer pods only after unique lease ownership and fencing are
  proven.

Higher worker counts should be adopted only when they reduce wall clock without
raising retry rate, dead letters, graph inconsistency, or NornicDB conflict
frequency.

## Acceptance Criteria

The reducer throughput phase is complete when:

- the 20-25 repo mixed corpus drains in less than `10m`,
- the 100 repo corpus drains in less than `30m`,
- the 896 repo corpus drains in less than `90m`, with a stretch target near the
  existing production expectation of `45m-55m`,
- failed and dead-letter queue counts remain `0`,
- graph/API truth checks pass for semantic entities, code calls, SQL
  relationships, workloads, and deployment mapping,
- the status surface can explain the slowest active domain without log mining,
- worker utilization drops only when no safe eligible work remains.

## Non-Goals

- Do not make NornicDB sequential reducer writes the final architecture.
- Do not blindly default worker count to vCPU count without conflict evidence.
- Do not tune timeouts as the primary solution.
- Do not remove semantic readiness gates to make wall-clock numbers look
  better.
- Do not run the full corpus for every speculative change.
- Do not add backend-specific branches outside documented adapter seams.

## Risks

- Narrowing conflict keys incorrectly can produce duplicate or missing graph
  edges.
- Increasing workers can worsen NornicDB contention if query shapes still scan
  or relationship probes remain expensive.
- Additional indexes can improve reads and writes while also increasing write
  amplification.
- Multi-pod reducers are unsafe until lease owners and ack/fail fencing are
  process-unique.
- Overfitting to one noisy repo can hide corpus-level behavior; every focused
  optimization still needs medium-corpus proof.

## Open Questions

- Which reducer domains are blocked by conflict policy versus graph write time?
- Which NornicDB writes are scanning despite available indexes?
- What is the safe partition key for code-call and repo-dependency shared
  runners?
- Does direct edge-between indexing remove the relationship `MERGE` hot path,
  or do PCG Cypher shapes still need label-specific splitting?
- How much of the tail remains after semantic entity graph writes are fixed?

## Phase 1 Runtime Evidence

The clean 20-repo proof after stopping outstanding remote runs used PCG
`0aa345d1`, rebuilt `pcg`, `pcg-api`, `pcg-ingester`, and `pcg-reducer`, and
ran against the first 20 repos from `/home/ubuntu/pcg-test-repos` with
NornicDB `v1.0.43` via the edge-index binary. `PCG_REDUCER_WORKERS` was unset;
the runtime logged the default `workers=8`.

Run `pcg-reducer-clean20-20260428T131056Z` drained healthy:

- wall clock from graph start to detected queue drain: `162s`;
- durable queue wall: projector `105.760s`, reducer `137.209s`;
- terminal state: projector `20` succeeded, reducer `158` rows succeeded,
  `pending=0`, `in_flight=0`, `retrying=0`, `dead_letter=0`, `failed=0`;
- reducer executions logged: `177` successes because deployment mapping
  re-executed during the local-authoritative reopen flow;
- reducer queue wait: `p50=5.579s`, `p95=61.525s`, `max=61.549s`;
- reducer handler duration: `p50=0.036s`, `p95=3.048s`, `max=11.979s`.

The slowest handler was
`sql_relationship_materialization/sql:api-php-sample-appwebsolutions`
(`11.979s` handler, `20.328s` queue wait). The largest queue-wait cluster was
deployment mapping at about `61.5s` with sub-second handlers, which points to
phase/readiness waiting rather than handler CPU. The largest source-local
projector item was `api-php-sample-appwebsolutions`: `153,902` facts,
`138,712` content entities, `66.356s` projector duration, and `37.291s`
canonical graph write.

The focused 4-repo proof used the repos that appeared in the 20-repo reducer
hot rows: `api-php-sample-appwebsolutions`, `portal-php-yc-soldwork`,
`api-node-communicator`, and `sample-service`.
Run `pcg-reducer-large4-20260428T131734Z` also drained healthy:

- wall clock from graph start to detected queue drain: `161s`;
- durable queue wall: projector `102.459s`, reducer `130.741s`;
- terminal state: projector `4` succeeded, reducer `32` rows succeeded,
  all failure classes null;
- reducer executions logged: `35` successes, again due deployment mapping
  re-execution;
- reducer queue wait: `p50=3.005s`, `p95=61.598s`, `max=72.458s`;
- reducer handler duration: `p50=0.389s`, `p95=6.759s`, `max=11.504s`.

This makes the 4-repo set a good next proof loop. It reproduces the largest
handler families without waiting for the full 20-repo corpus, and it keeps the
correctness surface broad enough to include service repos, deployment evidence,
SQL relationships, semantic materialization, and workload/deployment mapping.
The next optimization should not start by increasing worker counts. It should
explain why `api-php-sample-appwebsolutions` dominates SQL, semantic,
deployable-unit, workload, and deployment reducers, then prove whether the
primary fix is query shape, backend lookup behavior, or conflict/readiness
routing.

## Chunk Status

| Chunk | Status | Evidence | Next action |
| --- | --- | --- | --- |
| ADR baseline | Complete | 2026-04-28 full-corpus timing analysis captured here | Start reducer observability chunk |
| Reducer observability | In progress | Queue timing SQL proved queue wait dominates several domains. Commit `ec57b741` on branch `reducer-observability-phase1` adds `pcg_dp_reducer_queue_wait_seconds`, reducer `queue_wait_seconds`/`handler_duration_seconds` logs, and `/admin/status` `queue_blockages`; focused tests: `go test ./internal/reducer ./internal/status ./internal/storage/postgres -run 'TestServiceRunRecordsReducerQueueWait|TestBuildReportClassifiesProgressingQueue|TestRenderTextIncludesOperatorSummary|TestRenderJSONIncludesFlowSummaries|TestStatusStoreReadRawSnapshot' -count=1`. Remote proofs now include the noisy first 20-repo run, the clean 20-repo edge-index run `pcg-reducer-clean20-20260428T131056Z`, and the focused 4-repo run `pcg-reducer-large4-20260428T131734Z`; see Phase 1 Runtime Evidence above. | Add shared projection partition wait/processing split and top slow work-item run summary |
| Conflict matrix | Planned | Current conflict routing is safe but coarse | Map true conflict unit per reducer domain |
| Shared runner partitioning | Planned | Code-call and repo-dependency lanes still have global behavior | Partition by acceptance unit or repo scope |
| Cypher/index pilot | Planned | SQL and semantic paths show broad anchors and scan risk | Start with SQL relationship materialization |
| NornicDB backend proof | Planned | Backend write path has known edge-existence and validation costs | Benchmark exact PCG write shapes and upstream fixes |
| Concurrency proof | Planned | `8` workers completed healthy but too slowly | Test `16` workers only after telemetry and conflict fixes |
| Full-corpus acceptance | Planned | Baseline `7h43m40s` is unacceptable | Re-run full corpus after smaller proof ladder passes |
