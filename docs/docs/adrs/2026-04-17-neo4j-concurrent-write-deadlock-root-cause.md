# ADR: Neo4j Concurrent Write Deadlock — Accuracy and Performance Assessment

**Status:** Proposed
**Date:** 2026-04-17

## Context

After implementing the cross-phase EntityNotFound fixes (Options C + F + G
from the [previous ADR](2026-04-16-cross-phase-entity-not-found-race.md)),
a 6-hour E2E validation on the remote instance (ubuntu@10.208.198.57, 896
repos) revealed residual failures that exposed gaps in both the
implementation and the error-handling architecture.

This ADR is intentionally framed around two system goals:

1. **Accuracy:** the graph should converge to the correct state without
   exposing inconsistent intermediate states or dropping intents.
2. **Performance:** the system should sustain concurrent indexing without
   pathological retry churn or long tail latency in hot write paths.

The goal is not to prove every detail of Neo4j's internal lock manager. The
goal is to make a decision that is accurate enough to guide the next
performance-safe architecture step.

**Related:** The [Semantic Entity Queue Throughput](2026-04-17-semantic-entity-queue-throughput.md)
ADR addresses per-entity intent granularity that inflates the reducer queue
from ~889 per-repo intents to 51K+ per-entity intents. That queue pressure is
an important adjacent performance problem: it increases overall reducer load,
prolongs backlog drain, and can worsen retry recovery. It should be treated as
related supporting context, not as proof of the specific deadlock mechanism
analyzed here.

## E2E Results: Before and After

### Baseline (before any fixes)

| Metric | Value |
|--------|-------|
| Total reducer executions | ~10,249 |
| Succeeded | ~8,974 |
| Terminal failures | **1,281** (12.5%) |
| EntityNotFound | 1,061 |
| DeadlockDetected | 220 |

### After Options C + F + G

| Metric | Value |
|--------|-------|
| Total reducer executions | ~35,678 |
| Succeeded | 3,600+ (snapshot taken while run was still active) |
| Terminal failures | **0** |
| EntityNotFound | **0** (eliminated) |
| DeadlockDetected (terminal) | **0** (converted to retryable) |
| TransactionExecutionLimit | 2 (correctly retrying) |
| Retrying intents | 2 (0.006%) |

**Interpretation:** This snapshot is strong evidence that the correctness fix
for cross-phase visibility worked. It is not, by itself, enough evidence to
claim the remaining concurrent-write behavior is fully understood or fully
optimized.

## Root Cause Trace (with code paths)

### Root Cause 1: Non-Atomic Projector Writes (SOLVED — Option C)

**Symptom:** 1,061 `EntityNotFound` errors.

**Mechanism:** `CanonicalNodeWriter.Write()` executed Phases A-G as
separate Neo4j transactions. Phase A (`DETACH DELETE`) committed before
Phase D (`MERGE` new Files) ran, exposing a window where the reducer's
`MATCH (f:File {path: ...})` resolved a stale index entry pointing to a
deleted node.

**Code path:**
```
CanonicalNodeWriter.Write()           — go/internal/storage/neo4j/canonical_node_writer.go:49
  → buildRetractStatements()          — Phase A: DETACH DELETE (separate tx)
  → buildFileStatements()             — Phase D: MERGE new Files (separate tx)
                                         ↑ window between these two txns ↑
Reducer MATCH (f:File {path: ...})    — go/internal/storage/neo4j/semantic_entity.go
  → index resolves node ID            — valid at index read time
  → storage loads node                — DELETED between index read and load
  → Neo.ClientError.Statement.EntityNotFound
```

**Fix:** `CanonicalNodeWriter.Write()` now collects all phase statements
and dispatches them via `GroupExecutor.ExecuteGroup()` — a single
`session.ExecuteWrite()` transaction. The graph transitions atomically
from old state to new state.

**Result:** 1,061 → 0 EntityNotFound errors.

### Root Cause 2: Missing RetryableError for Neo4j Codes (SOLVED — Option F)

**Symptom:** All 220 `DeadlockDetected` errors were terminal.

**Mechanism:** `Neo.ClientError.Statement.EntityNotFound` is classified as
`ClientError` by Neo4j, NOT `TransientError`. The Neo4j Go driver does NOT
auto-retry `ClientError` codes. The reducer handlers wrapped errors with
`fmt.Errorf(...)`, which does not implement `reducer.RetryableError`. The
queue's `ReducerQueue.failIntent()` only re-enqueues errors where
`reducer.IsRetryable(cause)` returns true.

**Code path:**
```
EdgeWriter.WriteEdges()               — go/internal/storage/neo4j/edge_writer.go:79
  → ge.ExecuteGroup(ctx, stmts)       — Neo4j session.ExecuteWrite
  → Neo4j DeadlockDetected            — driver retries internally for 30s
  → returns error to handler
CodeCallMaterializationHandler        — go/internal/reducer/code_call_materialization.go
  → fmt.Errorf("write canonical code calls: %w", err)
Service.executeWithTelemetry()        — go/internal/reducer/service.go:284
  → s.WorkSink.Fail(ctx, intent, err) — passes error to queue
ReducerQueue.failIntent()             — go/internal/storage/postgres/reducer_queue.go:417
  → q.retryable(cause, attemptCount)  — calls reducer.IsRetryable(cause)
  → errors.As(cause, &retryable)      — finds *neo4jRetryableError ← NEW
  → failureClass = "reducer_retryable"
  → UPDATE SET status = 'retrying', visible_at = now + 30s
```

**Fix:** `WrapRetryableNeo4jError()` inspects the error chain for
`*neo4j.Neo4jError` with retryable codes and wraps them in
`*neo4jRetryableError` implementing `Retryable() bool`. Applied at the
`EdgeWriter` and `SemanticEntityWriter` error returns.

**Result:** 220 → 0 terminal DeadlockDetected errors.

### Root Cause 3: TransactionExecutionLimit Not Detectable (SOLVED)

**Symptom:** 2 `TransactionExecutionLimit` errors classified as terminal
failures in initial E2E run despite `WrapRetryableNeo4jError` being
present.

**Mechanism:** When `session.ExecuteWrite()` exhausts its internal 30s
retry budget, it returns `*TransactionExecutionLimit`. This type stores
inner errors in `Errors []error` but does NOT implement `Unwrap()`. This
means `errors.As(err, &neo4jErr)` — looking for `*neo4j.Neo4jError` — walks
the `Unwrap()` chain and finds nothing. The `WrapRetryableNeo4jError`
function originally only checked for `*neo4j.Neo4jError`, missing the
`TransactionExecutionLimit` wrapper entirely.

**Driver type definition:**
```go
// github.com/neo4j/neo4j-go-driver/v5/neo4j/internal/errorutil/retry.go
type TransactionExecutionLimit struct {
    Cause  string
    Errors []error  // NO Unwrap() method
}
// neo4j.TransactionExecutionLimit is a type ALIAS for errorutil.TransactionExecutionLimit
```

**Fix:** Added explicit `errors.As(err, &txLimit)` check for
`*neo4j.TransactionExecutionLimit` BEFORE the `*neo4j.Neo4jError` check.
This catches the driver's retry-exhaustion wrapper and marks it retryable
for the queue.

**Result:** Both intents now show `status: 'retrying'`,
`failure_class: 'reducer_retryable'` in Postgres.

### Root Cause 4: Misleading Failure Logs (KNOWN — cosmetic)

**Symptom:** Log shows `failure_class: "reducer_failure"` and
`status: "failed"` even for intents that are correctly retried.

**Mechanism:** `Service.recordReducerResult()` (service.go:339-341)
hardcodes `failure_class := "reducer_failure"` for ANY execution error.
This log fires at line 290, BEFORE `WorkSink.Fail()` at line 291 makes
the actual retry decision. The queue writes `"reducer_retryable"` to
Postgres (reducer_queue.go:435), but that's a DB update, not a log line.

**Impact:** Operators see `"reducer_failure"` in logs and think the intent
is terminal, when it's actually being retried. The authoritative source
for retry status is the `fact_work_items` table, not the log.

**Recommendation:** Fix the log to reflect the actual retry decision.
Either log after `Fail()` returns, or emit a separate log line from the
queue when it decides to retry. Low priority — does not affect correctness.

## The Remaining Deadlocks: Accuracy and Performance Analysis

### What Produces Them

With Options C + F + G implemented, there are exactly **2 remaining
deadlocks** out of ~35K reducer executions. Both are in
`code_call_materialization`. Both are `DeadlockDetected` that exhausted
the Neo4j driver's 30s internal retry budget (4 and 2 attempts
respectively).

**The Cypher:**
```cypher
-- go/internal/storage/neo4j/canonical.go:155-178
UNWIND $rows AS row
MATCH (source:Function|Class|File {uid: coalesce(row.caller_entity_id, ...)})
MATCH (target:Function|Class|File {uid: coalesce(row.callee_entity_id, ...)})
MERGE (source)-[rel:CALLS]->(target)
SET rel.confidence = 0.95, ...
```

**The concurrency model:**
- 4 reducer workers (`PCG_REDUCER_WORKERS=4` in docker-compose.yaml:349)
- Each worker claims and executes intents independently
- Two workers can process `code_call_materialization` for different repos
  simultaneously

**Leading mechanism hypothesis:**

Neo4j's error output shows the lock cycle occurs on shared `INDEX_ENTRY`
resources during concurrent `MATCH` + `MERGE` work. The `uid` property index
on `Function|Class|File` is global, so different reducer workers can contend
through the same index and relationship write path even when they are not
processing the exact same node payload.

```
Worker 1:
  MATCH (source {uid: "e_abc"})  → SHARED lock on INDEX_ENTRY(X)
  MATCH (target {uid: "e_def"})  → needs SHARED lock on INDEX_ENTRY(Y)
  MERGE CALLS edge               → needs EXCLUSIVE on relationship group

Worker 2:
  MATCH (source {uid: "e_ghi"})  → EXCLUSIVE lock on INDEX_ENTRY(Y) [from MERGE]
  MATCH (target {uid: "e_jkl"})  → needs SHARED lock on INDEX_ENTRY(X)
  → DEADLOCK CYCLE
```

Neo4j detects the cycle and kills one transaction. The driver retries it.
If contention persists (e.g., large batches keeping locks longer than the
retry window), the driver exhausts its 30s budget and returns
`TransactionExecutionLimit`.

**Concrete error from production:**
```
ForsetiClient[transactionId=3614, clientId=2] can't acquire
SHARED INDEX_ENTRY(-5908163244833332056) because it would form
this deadlock wait cycle:
INDEX_ENTRY(-5908163244833332056)-[EXCLUSIVE_OWNER]->(tx:3615)
  -[WAITING_FOR_EXCLUSIVE]->(INDEX_ENTRY(-1981977714668826977))
  -[SHARED_OWNER]->(tx:3614)
  -[WAITING_FOR_SHARED]->(INDEX_ENTRY(-5908163244833332056))
```

This is two transactions contending on two different B-tree index entries.
That strongly suggests concurrent edge materialization is the hot path, but
it does **not** prove every detail of the lock graph, nor does it prove repo
identity is irrelevant in all cases.

Two points remain important:

1. Shared global indexes make cross-worker contention plausible.
2. Our own transaction shape may be amplifying lock hold time. In particular,
   `EdgeWriter.WriteEdges()` now groups batches into a single transaction,
   which improves atomicity but can also widen the contention window for
   large `code_call_materialization` writes.

### How To Think About This For Accuracy and Performance

**Accuracy:** The system is in much better shape than before.

1. **The projector race is eliminated.** Atomic writes (Option C) ensure
   the graph transitions atomically. No more intermediate state visible
   to readers. This was the correctness bug, and the E2E evidence supports
   that it is fixed.

2. **Retry classification is now correct.** The queue can distinguish
   retryable Neo4j failures from terminal ones, which protects eventual
   convergence instead of dropping intents on transient database contention.

**Performance:** The system is not yet where we should declare victory.

3. **The remaining deadlocks are small in count but concentrated in one hot
   path.** Both observed cases occurred in `code_call_materialization`. That
   is a better signal for targeted contention reduction than for broad
   acceptance of the current concurrency model.

4. **Retry is a safety net, not a performance strategy.** A retry rate of
   0.006% is operationally small in this snapshot, but `TransactionExecutionLimit`
   means the driver spent up to its full retry budget under contention. That
   is exactly the kind of long-tail behavior we should treat as a throughput
   and latency smell.

5. **The right question is not "is the architecture broken?"** The right
   question is whether the current concurrency shape is the best trade-off
   for accurate indexing and predictable throughput. Today the answer is:
   the correctness direction looks good, but the `code_call_materialization`
   write path still deserves targeted contention reduction.

### When Would This Architecture Need Redesign?

The current approach should be reconsidered when:

| Scaling scenario | Expected impact |
|------------------|-----------------|
| 896 repos, 4 workers | Two observed deadlocks in `code_call_materialization`; acceptable for correctness, worth improving for tail latency |
| Higher repo counts with same hot path | Expect more retry pressure unless contention in edge writes is reduced |
| More reducer workers or multiple replicas | Increases overlapping edge writes and raises the odds of lock contention |
| Sustained retrying intents | Indicates retries are no longer just smoothing bursts and are starting to shape throughput |

**Threshold for redesign:** When deadlocked intents take more than one
retry to resolve (persistent contention), or when queue retry delay
materially impacts end-to-end indexing latency.

## Options for Further Reduction (If Needed)

### Option H: Move `code_call_materialization` Onto A Controlled Shared-Intent Lane

Treat `code_call_materialization` as a staged shared-write producer instead of
letting each reducer worker write CALLS edges directly to Neo4j.

Today the handler builds `SharedProjectionIntentRow`-shaped rows with
`ProjectionDomain=code_calls`, but it still calls `EdgeWriter.WriteEdges()`
directly from the reducer worker. A better shape is:

1. `code_call_materialization` extracts canonical CALLS rows.
2. Those rows are persisted as durable shared intents for `code_calls`.
3. A dedicated `code_calls` lane owns the actual Neo4j writes for that domain.
4. That lane processes one repo/run atomically and starts with deliberately
   conservative concurrency and batch size until telemetry shows higher
   parallelism is safe.

The extra constraint is important: the generic shared projection runner is not
safe for `code_calls` as-is. Its retract path is repo-wide, but its work
selection is partitioned by per-edge partition keys. That means separate
partitions for the same repo can retract each other's writes before all edges
are restored. `code_calls` therefore needs dedicated repo-atomic ownership, not
just generic shared-runner reuse.

```
Reducer Worker 1 ─┐
Reducer Worker 2 ─┤→ persist `code_calls` shared intents → dedicated repo-atomic `code_calls` lane → Neo4j
Reducer Worker 3 ─┤
Reducer Worker 4 ─┘

Other domains continue executing in parallel.
```

**Pros:**
- Uses the repo's existing shared-intent and partition-lease architecture
  instead of inventing a one-off execution path
- Targets the hot path we actually observed without penalizing unrelated domains
- Moves CALLS writes behind durable, observable work ownership
- Creates a natural place to add `code_calls`-specific tuning instead of
  relying on generic reducer worker concurrency
- Improves accuracy and recoverability because CALLS writes become explicit
  queued work instead of in-flight reducer side effects

**Cons:**
- Requires changing `code_call_materialization` from direct-write to
  emit-intent behavior
- The current shared projection runner uses global worker / partition / batch
  settings, so true `code_calls` isolation requires adding per-domain controls
  or a dedicated `code_calls` lane
- Needs an explicit initial policy for `code_calls` concurrency
- Adds one more durable stage before CALLS edges appear in Neo4j

**Assessment:** Best next step if the goal is accuracy plus predictable
throughput. It is more aligned with the architecture the repo already has than
asking reducer workers to keep doing direct hot-path Neo4j writes.

**Recommended starting policy for `code_calls`:**

- add one effective writer lane for `code_calls` specifically, either through
  per-domain shared-runner overrides or dedicated `code_calls` runner ownership
- keep other shared domains and reducer work parallel
- increase `code_calls` parallelism only after telemetry shows low retry churn
  and acceptable tail latency

The key idea is not "serialize everything forever." The key idea is "put the
hot path behind a domain-owned execution lane so concurrency is deliberate
instead of accidental."

### Option I: Global Neo4j Write Serializer

Route all Neo4j edge writes through a single serializer regardless of domain.

**Pros:**
- Strongest deadlock prevention story
- Simplest mental model for lock contention

**Cons:**
- Penalizes unrelated domains that may not be contention-prone
- Creates a larger throughput bottleneck than necessary
- Throws away the domain-aware partitioning direction already present in the
  shared projection design

**Assessment:** Appropriate for a multi-replica, high-throughput deployment.
Too broad as the first response.

### Option J: Reduce Global Reducer Concurrency (Blunt Instrument)

Set `PCG_REDUCER_WORKERS=2` or add domain-level parallelism control so
only one worker processes `code_call_materialization` at a time while other
domains remain parallel.

**Pros:**
- One line of config change
- Immediately reduces deadlock probability

**Cons:**
- If applied globally, reduces throughput for all domains, not just code_call
- Does not tell us whether the hot path is domain-specific or truly global
- Easy to keep forever for the wrong reason

**Assessment:** Reasonable as an emergency mitigation. Inferior to
domain-specific serialization if the goal is better accuracy/performance
trade-offs.

## Decision

**Accepted as a correctness improvement, not yet accepted as a final
performance shape.** The fixes implemented (Options C + F + G +
TransactionExecutionLimit detection) address the known correctness issues and
ensure retryable Neo4j failures are no longer dropped as terminal failures.
The `code_calls` lane refactor described here has now been implemented in its
first conservative form: reducer workers emit durable `code_calls` intents, the
generic shared runner no longer owns `code_calls`, and a dedicated repo-atomic
runner performs the actual Neo4j writes.

**The preferred next step is to move `code_call_materialization` onto a
controlled shared-intent lane for `code_calls`, then run that lane with
conservative concurrency until telemetry proves a higher-performance setting is
safe.**

Specifically:

1. Keep the atomic projector write change.
2. Keep retryable Neo4j error classification.
3. Stop treating direct CALLS edge writes from arbitrary reducer workers as the
   desired steady-state architecture.
4. Reframe `code_call_materialization` as a producer of durable `code_calls`
   intents, with explicit repo-atomic `code_calls` execution control owning the
   actual Neo4j write.
5. Prefer Option H over global worker reduction if further E2E evidence shows
   recurring contention.

**What we are not claiming:**

- We are not claiming the exact Neo4j lock graph is fully proven.
- We are not claiming shared global index contention is the only mechanism.
- We are not claiming current retry behavior alone is the desired end-state.

## Action Items

| Item | Status | Priority |
|------|--------|----------|
| Remove debug logging from `retryable_error.go` | Done | P0 |
| Fix misleading `failure_class: "reducer_failure"` log (Root Cause 4) | TODO | P2 |
| Monitor retrying intents to confirm they succeed on next attempt | TODO | P0 |
| Implement per-repo semantic entity intent consolidation ([throughput ADR](2026-04-17-semantic-entity-queue-throughput.md)) | TODO | P0 |
| Measure latency and retry behavior specifically for `code_call_materialization` / `code_calls` | TODO | P1 |
| Prototype `code_call_materialization` as a durable `code_calls` shared-intent producer | Done | P1 |
| Add per-domain execution control for `code_calls` instead of relying only on global shared-runner settings | Done | P1 |
| Add a conservative concurrency policy for the `code_calls` shared lane before increasing throughput | Done | P1 |
| Add `pcg_dp_neo4j_deadlock_retries_total` counter for dashboards | TODO | P1 |
| Document `TransactionExecutionLimit` behavior in operator runbook | TODO | P1 |
| Reconcile reducer/shared-projection default-concurrency docs with current code and compose defaults | TODO | P1 |

## Key Source Files

| File | Relevance |
|------|-----------|
| `go/internal/storage/neo4j/retryable_error.go` | RetryableError wrapper for Neo4j codes + TransactionExecutionLimit |
| `go/internal/storage/neo4j/retryable_error_test.go` | Table-driven tests including production error chain replication |
| `go/internal/storage/neo4j/edge_writer.go` | EdgeWriter applies WrapRetryableNeo4jError at error returns |
| `go/internal/storage/neo4j/canonical_node_writer.go` | Atomic Phase A-G via GroupExecutor |
| `go/internal/storage/neo4j/canonical.go:155-178` | Code call upsert Cypher (deadlock-prone MATCH+MERGE) |
| `go/internal/reducer/code_call_materialization.go` | Reducer handler now emits durable `code_calls` intents instead of direct Neo4j writes |
| `go/internal/reducer/code_call_projection_runner.go` | Dedicated repo-atomic `code_calls` execution lane |
| `go/internal/reducer/shared_projection_runner.go` | Generic shared-intent runner; `code_calls` removed from this path because repo-wide retract + per-edge partitioning is unsafe |
| `go/internal/reducer/service.go:284-294` | Worker loop: execute → log → fail (log before retry decision) |
| `go/internal/reducer/service.go:339-341` | Hardcoded `failure_class: "reducer_failure"` in logger |
| `go/internal/storage/postgres/reducer_queue.go:413-454` | Queue retry decision (`retryable()` → `failIntent()`) |
| `go/internal/reducer/intent.go:81-97` | `RetryableError` interface and `IsRetryable()` |
| `go/cmd/reducer/config.go:40-52` | Worker count: `PCG_REDUCER_WORKERS`, default min(NumCPU, 4) |
| `go/internal/reducer/shared_projection_runner.go:348-360` | Shared projection defaults differ from docs and should be reconciled |
| `docker-compose.yaml:349-352` | Compose defaults: reducer/shared projection concurrency and batch settings |
| `neo4j-go-driver/.../errorutil/retry.go` | `TransactionExecutionLimit` — no `Unwrap()` method |
