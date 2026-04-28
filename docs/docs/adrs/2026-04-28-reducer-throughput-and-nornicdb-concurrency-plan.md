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
ran against the first 20 repos from the remote test corpus with NornicDB
`v1.0.43` via the edge-index binary. `PCG_REDUCER_WORKERS` was unset; the
runtime logged the default `workers=8`.

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
`sql_relationship_materialization/sql:api-php-boatwizardwebsolutions`
(`11.979s` handler, `20.328s` queue wait). The largest queue-wait cluster was
deployment mapping at about `61.5s` with sub-second handlers, which points to
phase/readiness waiting rather than handler CPU. The largest source-local
projector item was `api-php-boatwizardwebsolutions`: `153,902` facts,
`138,712` content entities, `66.356s` projector duration, and `37.291s`
canonical graph write.

The focused 4-repo proof used the repos that appeared in the 20-repo reducer
hot rows: `api-php-boatwizardwebsolutions`, `portal-php-yc-soldboats`,
`api-node-communicator`, and `api-node-boats`.
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
explain why `api-php-boatwizardwebsolutions` dominates SQL, semantic,
deployable-unit, workload, and deployment reducers, then prove whether the
primary fix is query shape, backend lookup behavior, or conflict/readiness
routing.

Every fresh performance proof after this point must capture host resource
headroom alongside queue timings: CPU idle, disk I/O idle or utilization,
run wall time, queue wait, handler duration, conflict blocking, and graph
backend query/write timing. Reducer speed work must classify the bottleneck as
Cypher/query shape, graph index or lookup behavior, data shape/write
amplification, conflict routing, or real CPU/disk saturation before changing
worker defaults.

The first resource-headroom proof on the focused 4-repo corpus used commit
`9c0b6207`, rebuilt all runtime binaries, kept `PCG_REDUCER_WORKERS` unset, and
captured CPU idle plus disk utilization during the run. Run
`pcg-reducer-large4-resource-baseline-20260428T141520Z` drained healthy:

- wall clock from graph start to detected queue drain: `153s`;
- terminal state: projector `4` succeeded, reducer `32` rows succeeded, with
  `pending=0`, `in_flight=0`, `retrying=0`, `dead_letter=0`, `failed=0`;
- `cpu_idle_avg=80.58%`, `cpu_idle_p50=86.00%`, `cpu_idle_min=22.00%`;
- `disk_util_avg=1.28%`, `disk_util_max=46.72%`, so disk idle never fell below
  about `53%`;
- slowest handler:
  `sql_relationship_materialization/sql:api-php-boatwizardwebsolutions`
  (`11.433s` handler, `20.358s` queue wait);
- slowest waits were `deployment_mapping` rows at about `100.9s`, while their
  handlers stayed sub-second.

This evidence rules out host CPU or disk saturation as the primary bottleneck
for the focused corpus. The next useful questions are why eligible work waits,
where shared projection backlog accumulates, and whether graph write/query
shapes are forcing backend-side scans or serialized existence checks.

The first Cypher-shape pilot used commit `55740672`, which writes SQL
relationship rows with concrete source and target entity labels when the
reducer knows them, while preserving broad-label fallback for older queued rows.
Run `pcg-reducer-large4-sql-labelscope-20260428T142359Z` also rebuilt all
runtime binaries and drained healthy:

- wall clock from graph start to detected queue drain: `154s`;
- terminal state: projector `4` succeeded, reducer `32` rows succeeded, with
  `pending=0`, `in_flight=0`, `retrying=0`, `dead_letter=0`, `failed=0`;
- `cpu_idle_avg=80.74%`, `cpu_idle_p50=86.00%`, `cpu_idle_min=22.00%`;
- `disk_util_avg=1.28%`, `disk_util_max=46.00%`, so disk idle never fell below
  about `54%`;
- slowest SQL handler changed from `11.433s` to `11.702s`, and total wall
  changed from `153s` to `154s`.

The label-scoped SQL write shape is more selective and keeps the adapter on a
clear label-property anchor, but this proof did not improve the focused corpus.
That disproves broad SQL labels as the dominant current wall-clock cause for
these repos. The next reducer slice should split shared projection
wait-versus-processing evidence and investigate deployment/readiness routing
before spending more time on SQL label-shape tuning.

Commit `b0c994b6` adds the shared projection wait-versus-processing split for
that next proof. The runner now records selected intent age with
`outcome=processed`, readiness-blocked selected intent age with
`outcome=readiness_blocked`, and graph-write/completion processing duration
after partition selection. It also logs blocked readiness wait, lease-claim
duration, selection duration, and processing duration for completed shared
projection cycles. This does not change claim order, partition count, worker
count, readiness gates, or graph-write behavior.

Run `pcg-reducer-large4-shared-telemetry-20260428T144634Z` used commit
`766fb142`, rebuilt all runtime binaries, kept `PCG_REDUCER_WORKERS` unset
(`workers=8`), and reran the same focused 4-repo corpus. It drained healthy:

- wall clock from graph start to detected queue drain: `138s`;
- terminal state: projector `4` succeeded, reducer `32` rows succeeded, with
  `pending=0`, `in_flight=0`, `retrying=0`, `dead_letter=0`, `failed=0`;
- durable source-local projector wall: `102.315s`;
- durable reducer wall by longest domain: `sql_relationship_materialization`
  `130.129s`;
- CPU remained idle-heavy: `cpu_idle_avg=79.25%`, `cpu_idle_p50=85.00%`,
  `cpu_idle_min=24.00%`;
- disk stayed below saturation: `disk_util_avg=9.34%`,
  `disk_util_p50=4.94%`, `disk_util_max=48.00%`.

The largest reducer waits were still reopened `deployment_mapping` rows for the
smaller repos at about `61.29s` queue wait with `0.15s`, `0.16s`, and `1.08s`
handlers. The largest handler remained
`sql_relationship_materialization/sql:api-php-boatwizardwebsolutions`
(`11.165s` handler, `19.439s` queue wait). The large PHP repo also produced
the next cluster of `5.6s-6.7s` handlers across code-call, deployable-unit,
inheritance, semantic, deployment, and workload domains.

The important new signal is the shared follow-up lane. The run wrote only
`code_calls` shared projection intents: `3869` total, `3869` completed, with
`119.682s` wall. Code-call projection logs showed repeated readiness-blocked
cycles while canonical nodes for the large PHP repo were not committed, then a
final large cycle wrote `2851` rows in `4.019s`. The smaller repos wrote `244`,
`105`, and `665` rows in `0.187s`, `0.157s`, and `0.719s`. That means the
focused shared follow-up wall was dominated by readiness/polling and the
source-local canonical long pole, not by code-call graph write duration.

This also exposed an observability seam: `code_calls` shared intents are owned
by the dedicated code-call projection runner, not the generic
`SharedProjectionRunner` that commit `b0c994b6` instrumented. The next
observability slice should add the same wait-versus-processing split to the
code-call projection runner before changing code-call worker counts or
partitioning.

Commit `742d0c56` closes that seam for the dedicated code-call projection
runner. The runner now reports selected intent wait, readiness-blocked intent
wait, selection duration, lease-claim duration, and graph-write/completion
processing duration through the same shared projection histograms and structured
cycle logs used by the generic shared projection runner. The change preserves
lease scope, readiness gating, acceptance-unit selection, graph write shape, and
worker defaults. Focused verification:

- `go test ./internal/reducer -run 'TestCodeCallProjectionRunnerProcessesRepoAtomically|TestCodeCallProjectionRunnerProcessOnceReportsReadinessBlockedWait|TestCodeCallProjectionRunnerRecordCycleUsesAcceptanceLogKeys' -count=1`;
- `go test ./internal/reducer ./internal/telemetry -count=1`;
- `go vet ./internal/reducer ./internal/telemetry`;
- `uv run --with mkdocs --with mkdocs-material --with pymdown-extensions mkdocs build --strict --clean --config-file docs/mkdocs.yml`;
- `git diff --check`.

The next runtime proof should rerun the focused 4-repo corpus with commit
`742d0c56` and inspect `domain=code_calls` wait versus processing fields before
changing polling, readiness publication, partitioning, or worker counts.

Run `pcg-reducer-large4-codecall-telemetry-20260428T161400Z` used commit
`e0a407ae` with rebuilt binaries and the same focused 4-repo corpus. It drained
healthy in `141s`, which is effectively no performance improvement over the
prior `138s` run and should be treated as instrumentation evidence rather than
an optimization. Durable state ended at projector `4` succeeded and reducer `32`
succeeded. Host resources remained underused: `cpu_idle_avg=88.45%`,
`cpu_idle_p50=97.00%`, `cpu_idle_min=21.00%`, `disk_util_avg=5.49%`,
`disk_util_p50=4.87%`, and `disk_util_max=44.40%`.

The dedicated code-call telemetry showed `code_calls` shared projection intents
at `3870` total and `3870` completed with `124.162s` table wall. Completed
code-call cycles, however, spent only about `10.85s` in measured processing:
small repos processed `105`, `244`, and `665` rows in `0.142s`, `0.214s`, and
`0.800s`; the large PHP repo processed `2852` rows in `9.696s`. Readiness-blocked
logs fired `25` times with max blocked wait `18.653s`; the largest completed
cycle selected-intent wait was `22.727s`. This confirms the shared lane wall is
mostly not code-call graph-write CPU time. The next optimization proof should
focus on readiness publication/polling and source-local canonical/content
projection timing, while separately keeping an eye on the large PHP code-call
write and SQL handler shapes.

Commit `3e870754` applies the first small readiness-polling optimization from
that evidence. Readiness-blocked code-call cycles now wait the configured base
poll interval instead of being treated like empty cycles that exponentially
back off toward `5s`. On the `e0a407ae` proof this targets the visible tail
where the final PHP code-call cycle started about `4s` after the last blocked
readiness log; it should save seconds per readiness-blocked repo/run, not
hours by itself. The change does not alter readiness gates, acceptance-unit
selection, leases, worker defaults, or graph writes. Verification:

- `go test ./internal/reducer -run 'TestCodeCallProjectionRunnerUsesBasePollIntervalWhileReadinessBlocked|TestCodeCallProjectionRunnerRunContinuesAfterCycleError|TestCodeCallProjectionRunnerProcessOnceReportsReadinessBlockedWait' -count=1`;
- `go test ./internal/reducer ./internal/telemetry -count=1`;
- `go vet ./internal/reducer ./internal/telemetry`.

Run `pcg-reducer-large4-readiness-poll-20260428T163313Z` used commit
`11d74089` with rebuilt binaries and the same focused 4-repo corpus. It drained
healthy in `139s`, which is effectively flat versus the prior `141s` and `138s`
proofs. This confirms the code-call readiness polling change is a tail-latency
cleanup, not the main reducer throughput win. Durable state ended at projector
`4` succeeded and reducer `32` succeeded. Host resources again showed headroom:
`cpu_idle_avg=77.10%`, `cpu_idle_p50=87.00%`, `cpu_idle_min=24.00%`,
`disk_util_avg=9.33%`, `disk_util_p50=4.86%`, and `disk_util_max=44.40%`.

The same run sharpens the next reducer targets. `code_calls` completed `3870`
shared intents with `119.767s` table wall, but measured completed code-call
cycles spent only about `5.12s` in processing for `3866` written rows; the
largest cycle wrote the PHP repo's `2852` rows in `3.98s` processing and
`4.04s` total. Readiness-blocked code-call logs fired more frequently under the
base poll interval (`122` observations, max blocked wait `18.979s`), but wall
time stayed bounded by other reducer dependencies. Reducer handler evidence now
points at `sql_relationship_materialization` (`handler_max=11.325s`,
`queue_wait_max=73.366s`, `handler_sum=13.232s`) and deployment mapping queue
wait (`queue_wait_sum=200.698s` with only `8.530s` handler sum) before any
worker-count change.

Commit `02d9cdc7` applies the same readiness-polling correction to the generic
shared projection runner. Readiness-blocked SQL and inheritance shared
projection partitions now wait the configured base poll interval instead of
being counted as empty cycles that exponentially back off. The change preserves
readiness gates, lease scope, partition count, worker defaults, and graph write
shape; it only keeps known readiness-blocked reducer work responsive. Focused
verification:

- `go test ./internal/reducer -run 'TestSharedProjectionRunnerUsesBasePollIntervalWhileReadinessBlocked|TestSharedProjectionRunnerBackoffOnEmptyCycles|TestSharedProjectionRunnerBackoffResetsOnWork' -count=1`;
- `go test ./internal/reducer ./internal/telemetry -count=1`;
- `go vet ./internal/reducer ./internal/telemetry`;
- `git diff --check`.

Commit `acc50494` narrows the NornicDB local-authoritative projector-drain
claim gate from global to same-scope. Reducer graph writes still wait for
source-local projection for their own `scope_id`, preserving the same-scope
destructive-write correctness gate, but unrelated repos can drain reducer work
while a large repo is still in source-local projection. Focused verification:

- `go test ./internal/storage/postgres -run 'TestReducerQueueClaimCanWaitForProjectorDrain|TestClaimBatchCanWaitForProjectorDrain' -count=1`;
- `go test ./internal/storage/postgres ./internal/reducer -count=1`;
- `go vet ./internal/storage/postgres ./internal/reducer`;
- `git diff --check`.

Run `pcg-reducer-large4-scope-drain-fresh-20260428T164757Z` used commit
`acc50494` with rebuilt binaries and the same focused 4-repo corpus. It drained
healthy in `140s`, so wall time stayed effectively flat versus the `139s`,
`141s`, and `138s` proofs. The scheduling evidence changed materially,
however: deployment-mapping reducer queue wait dropped from `200.698s` summed
wait in the prior proof to `14.618s`, and SQL relationship reducer queue wait
dropped from `101.708s` to `33.651s`. The run completed with projector `4`
succeeded, reducer `32` succeeded, no failed/dead-letter work, and
`code_calls` shared intents `3870/3870` completed.

The remaining wall-clock long pole is now explicit. Source-local projection
still had `103.328s` durable wall and the largest repo still spent `59.909s`
in `project_generation`, `37.082s` in canonical graph write, and `21.133s` in
content write. Reducer-side SQL handler cost remains the highest handler slice:
`sql_relationship_materialization` had `handler_sum=13.163s` and
`handler_max=11.543s`. Host resources remained underused:
`cpu_idle_avg=79.00%`, `cpu_idle_p50=87.00%`, `cpu_idle_min=26.00%`,
`disk_util_avg=9.51%`, `disk_util_p50=4.85%`, and `disk_util_max=41.20%`.
This proves the scoped gate removes false reducer serialization but is not
enough by itself; the next reducer-owned optimization should split or reshape
the SQL relationship write path and continue conflict-domain analysis for
same-repo final reducers.

Commit `367060fd` scopes grouped SQL relationship retractions by exact source
label and relationship type while preserving the existing broad single-statement
fallback for execute-only callers. This removes the NornicDB-unfriendly grouped
shape `MATCH (source)-[rel:REFERENCES_TABLE|HAS_COLUMN|TRIGGERS]->()` from the
normal reducer grouped path. Focused verification:

- `go test ./internal/storage/neo4j -count=1`;
- `go test ./internal/reducer -run 'TestSQLRelationship|TestExtractSQLRelationship' -count=1`;
- `go test ./internal/storage/neo4j ./internal/reducer -count=1`;
- `go vet ./internal/storage/neo4j ./internal/reducer`;
- `git diff --check`.

Run `pcg-reducer-large4-sql-retract-scope-20260428T170204Z` used commit
`367060fd` with rebuilt binaries and the same focused 4-repo corpus. It drained
healthy in `138s` with projector `4` succeeded, reducer `32` succeeded, no
failed/dead-letter work, and `code_calls` shared intents `3870/3870`
completed. The SQL handler moved only slightly:
`sql_relationship_materialization` had `handler_sum=12.275s` and
`handler_max=10.634s`, versus `13.163s` and `11.543s` in the scoped-drain
proof. SQL reducer queue wait stayed effectively the same (`32.946s` summed
wait versus `33.651s`). Host resources again had headroom:
`cpu_idle_avg=78.90%`, `cpu_idle_p50=86.00%`, `cpu_idle_min=23.00%`,
`disk_util_avg=14.48%`, `disk_util_p50=12.90%`, `disk_util_max=49.80%`, and
`disk_idle_avg=85.52%`.

This proves the scoped SQL retraction shape is safe and marginally cleaner, but
not a meaningful wall-clock reducer fix on this 4-repo proof. The next reducer
slice should either add inner-step SQL handler timing (`ListFacts`, extraction,
retract, write) or shift to the larger measured full-corpus reducer cost:
semantic entity materialization query/write shape.

## Chunk Status

| Chunk | Status | Evidence | Next action |
| --- | --- | --- | --- |
| ADR baseline | Complete | 2026-04-28 full-corpus timing analysis captured here | Start reducer observability chunk |
| Reducer observability | In progress | Queue timing SQL proved queue wait dominates several domains. Commit `ec57b741` on branch `reducer-observability-phase1` adds `pcg_dp_reducer_queue_wait_seconds`, reducer `queue_wait_seconds`/`handler_duration_seconds` logs, and `/admin/status` `queue_blockages`; focused tests: `go test ./internal/reducer ./internal/status ./internal/storage/postgres -run 'TestServiceRunRecordsReducerQueueWait|TestBuildReportClassifiesProgressingQueue|TestRenderTextIncludesOperatorSummary|TestRenderJSONIncludesFlowSummaries|TestStatusStoreReadRawSnapshot' -count=1`. Remote proofs now include the clean 20-repo edge-index run `pcg-reducer-clean20-20260428T131056Z`, the focused 4-repo run `pcg-reducer-large4-20260428T131734Z`, the resource-headroom baseline `pcg-reducer-large4-resource-baseline-20260428T141520Z`, the SQL label-scope pilot `pcg-reducer-large4-sql-labelscope-20260428T142359Z`, the shared telemetry run `pcg-reducer-large4-shared-telemetry-20260428T144634Z`, the code-call telemetry run `pcg-reducer-large4-codecall-telemetry-20260428T161400Z`, the code-call readiness-poll run `pcg-reducer-large4-readiness-poll-20260428T163313Z`, the scoped projector-drain run `pcg-reducer-large4-scope-drain-fresh-20260428T164757Z`, and the SQL retraction-scope run `pcg-reducer-large4-sql-retract-scope-20260428T170204Z`; see Phase 1 Runtime Evidence above. Commit `9c0b6207` adds `PCG_REDUCER_CLAIM_DOMAIN` for split-reducer diagnostics without changing all-domain defaults. Commit `55740672` adds label-scoped SQL relationship writes, but the 4-repo proof showed no wall-clock improvement (`153s` to `154s`) and SQL handler max stayed about `11s`. CPU and disk remained mostly idle in fresh runs, so the next bottleneck is not host saturation. Commit `b0c994b6` adds `pcg_dp_shared_projection_intent_wait_seconds`, `pcg_dp_shared_projection_processing_seconds`, and shared projection logs for readiness-blocked wait, lease claim, selection, and processing durations; focused verification: `go test ./internal/reducer ./internal/telemetry -count=1`, `go vet ./internal/reducer ./internal/telemetry`, `mkdocs build --strict`, and `git diff --check`. The 4-repo rerun on `766fb142` drained in `138s`; `code_calls` shared intents had `119.682s` wall but only about `5.08s` summed graph-write cycle duration, exposing readiness/polling and source-local canonical projection as the immediate bottleneck for that lane. Commit `742d0c56` adds the same wait-versus-processing split to the dedicated code-call projection runner, including processed intent wait, readiness-blocked wait, selection duration, lease claim duration, and processing duration logs/metrics without changing worker defaults or graph writes. The `e0a407ae` remote proof drained in `141s`; `code_calls` table wall was `124.162s` but measured code-call processing summed to about `10.85s`, while CPU and disk stayed idle-heavy. Commit `3e870754` keeps readiness-blocked code-call polling at the base interval instead of exponential empty-queue backoff; the `11d74089` runtime proof drained in `139s`, confirming this is a small tail cleanup. Commit `02d9cdc7` applies the same base-poll behavior to generic shared projection readiness-blocking for SQL and inheritance lanes. Commit `acc50494` narrows the NornicDB projector-drain claim gate to same-scope projector work; the `acc50494` runtime proof drained in `140s`, but deployment-mapping summed queue wait dropped to `14.618s` and SQL summed queue wait dropped to `33.651s`. Commit `367060fd` scopes grouped SQL relationship retractions; the `367060fd` runtime proof drained in `138s`, SQL handler max moved only from `11.543s` to `10.634s`, and CPU/disk still had headroom. | Add inner-step timing for reducer SQL materialization or move to semantic entity materialization query/write shape, which is the largest full-corpus reducer work cost |
| Conflict matrix | Planned | Current conflict routing is safe but coarse | Map true conflict unit per reducer domain |
| Shared runner partitioning | Planned | Code-call and repo-dependency lanes still have global behavior | Partition by acceptance unit or repo scope |
| Cypher/index pilot | Planned | SQL and semantic paths show broad anchors and scan risk | Start with SQL relationship materialization |
| NornicDB backend proof | Planned | Backend write path has known edge-existence and validation costs | Benchmark exact PCG write shapes and upstream fixes |
| Concurrency proof | Planned | `8` workers completed healthy but too slowly | Test `16` workers only after telemetry and conflict fixes |
| Full-corpus acceptance | Planned | Baseline `7h43m40s` is unacceptable | Re-run full corpus after smaller proof ladder passes |
