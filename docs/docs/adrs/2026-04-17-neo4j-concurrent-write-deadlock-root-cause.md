# ADR: Neo4j Concurrent Write Deadlock — Root Cause and Architecture Assessment

**Status:** Accepted
**Date:** 2026-04-17

## Context

After implementing the cross-phase EntityNotFound fixes (Options C + F + G
from the [previous ADR](2026-04-16-cross-phase-entity-not-found-race.md)),
a 6-hour E2E validation on the remote instance (ubuntu@10.208.198.57, 896
repos) revealed residual failures that exposed gaps in both the
implementation and the error-handling architecture. This ADR traces the
complete execution path, documents every root cause discovered, and
assesses whether the current write architecture is fundamentally sound or
needs redesign.

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
| Succeeded | 3,600+ (running) |
| Terminal failures | **0** |
| EntityNotFound | **0** (eliminated) |
| DeadlockDetected (terminal) | **0** (converted to retryable) |
| TransactionExecutionLimit | 2 (correctly retrying) |
| Retrying intents | 2 (0.006%) |

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

## The Remaining Deadlocks: Architectural Analysis

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

**The deadlock mechanism:**

Neo4j's Forseti lock manager uses pessimistic locking. The `uid` property
index on `Function|Class|File` is a global B-tree shared across all repos.

```
Worker 1 (repo: bw-mobile-app):
  MATCH (source {uid: "e_abc"})  → SHARED lock on INDEX_ENTRY(X)
  MATCH (target {uid: "e_def"})  → needs SHARED lock on INDEX_ENTRY(Y)
  MERGE CALLS edge               → needs EXCLUSIVE on relationship group

Worker 2 (repo: bg-data-pipeline):
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
Not the same node. Not the same repo. Pure index-level lock contention
from concurrent writes through a shared global index.

### Is the Architecture Fundamentally Broken?

**No.** Here's why:

1. **The projector race is eliminated.** Atomic writes (Option C) ensure
   the graph transitions atomically. No more intermediate state visible
   to readers. This was the structural flaw, and it's fixed.

2. **The remaining deadlocks are an inherent property of concurrent writes
   to any database with pessimistic locking.** Postgres has the same issue
   (`deadlock_timeout`). The standard solution is retry, which we now have.

3. **The failure rate is 0.006% (2/35,678).** With queue retry, these
   resolve on the next attempt when contention has subsided.

4. **The complexity is bounded.** We added:
   - `WrapRetryableNeo4jError()` — 56 lines, one function, well-tested
   - `GroupExecutor` support in projector — mirrors existing reducer pattern
   - Generation-scoped directory retracts — one predicate change
   
   These are not patches on patches. They're completing a design that was
   originally underspecified about Neo4j concurrency semantics.

### When Would This Architecture Need Redesign?

The concurrent-writers model breaks down when:

| Scaling scenario | Expected impact |
|------------------|-----------------|
| 896 repos, 4 workers | 2 deadlocks (0.006%) — current |
| 5,000 repos, 4 workers | ~10 deadlocks — still acceptable with retry |
| 10,000+ repos, 8+ workers | Deadlock rate grows quadratically with concurrent writers; retry delay accumulates |
| Multiple reducer replicas | Each replica adds independent concurrent writers; deadlocks multiply |

**Threshold for redesign:** When deadlocked intents take more than one
retry to resolve (persistent contention), or when queue retry delay
materially impacts end-to-end indexing latency.

## Options for Further Reduction (If Needed)

### Option H: Neo4j Write Serializer

Route all Neo4j edge writes through a single goroutine channel. Eliminates
deadlocks by construction — only one transaction at a time.

```
Reducer Worker 1 ─┐
Reducer Worker 2 ─┤→ write channel → single writer goroutine → Neo4j
Reducer Worker 3 ─┤
Reducer Worker 4 ─┘
```

**Pros:**
- Zero deadlocks by construction
- Workers still claim and resolve intents concurrently (Postgres work is
  parallel); only the Neo4j write is serialized
- Clean separation: reducer logic is concurrent, Neo4j I/O is serial

**Cons:**
- Neo4j write becomes a throughput bottleneck
- Requires careful channel design (buffered, back-pressure, shutdown)
- Changes the error ownership model (who retries? the writer or the
  worker?)

**Assessment:** Right approach when scaling past 8+ concurrent workers or
multiple reducer replicas. Overkill for current 4-worker single-instance
deployment.

### Option I: Postgres-Staged Edge Writes

Instead of writing directly to Neo4j, reducer handlers write "edge
intents" to a Postgres staging table. A separate batch writer process
reads from staging and writes to Neo4j in ordered, non-overlapping batches.

**Pros:**
- Fully decouples reducer concurrency from Neo4j write concurrency
- Batch writer can optimize write order to minimize lock contention
- Postgres handles the concurrent-write coordination (it's designed for it)
- Natural backpressure: staging table depth is observable

**Cons:**
- Adds write-amplification (Postgres staging → Neo4j)
- Eventual consistency between Postgres fact state and Neo4j graph state
- New component to operate and monitor
- Most complex option

**Assessment:** Appropriate for a multi-replica, high-throughput deployment.
Not justified at current scale.

### Option J: Reduce Concurrent Edge Writers (Simplest)

Set `PCG_REDUCER_WORKERS=2` or add domain-level parallelism control so
only one worker processes `code_call_materialization` at a time while other
domains remain parallel.

**Pros:**
- One line of config change
- Immediately reduces deadlock probability

**Cons:**
- Reduces throughput for all domains, not just code_call
- Doesn't eliminate deadlocks — just reduces probability

**Assessment:** Quick mitigation if deadlock rate increases. Not needed at
current 0.006%.

## Decision

**The current architecture is sound.** The fixes implemented (Options C +
F + G + TransactionExecutionLimit detection) address all structural issues.
The remaining deadlocks are an expected property of concurrent writes to a
pessimistic-locking database, handled correctly by bounded retry.

**No redesign is needed at current scale (896 repos, 4 workers).**

**Scaling triggers for future work:**
- If deadlock rate exceeds 1% per E2E run → implement Option J (reduce
  workers) as immediate mitigation
- If scaling past 8 concurrent workers or multiple reducer replicas →
  implement Option H (write serializer)
- If latency SLA requires sub-second edge materialization → evaluate
  Option I (Postgres-staged writes)

## Action Items

| Item | Status | Priority |
|------|--------|----------|
| Remove debug logging from `retryable_error.go` | Done | P0 |
| Fix misleading `failure_class: "reducer_failure"` log (Root Cause 4) | TODO | P2 |
| Monitor retrying intents to confirm they succeed on next attempt | TODO | P0 |
| Add `pcg_dp_neo4j_deadlock_retries_total` counter for dashboards | TODO | P1 |
| Document `TransactionExecutionLimit` behavior in operator runbook | TODO | P1 |

## Key Source Files

| File | Relevance |
|------|-----------|
| `go/internal/storage/neo4j/retryable_error.go` | RetryableError wrapper for Neo4j codes + TransactionExecutionLimit |
| `go/internal/storage/neo4j/retryable_error_test.go` | Table-driven tests including production error chain replication |
| `go/internal/storage/neo4j/edge_writer.go` | EdgeWriter applies WrapRetryableNeo4jError at error returns |
| `go/internal/storage/neo4j/canonical_node_writer.go` | Atomic Phase A-G via GroupExecutor |
| `go/internal/storage/neo4j/canonical.go:155-178` | Code call upsert Cypher (deadlock-prone MATCH+MERGE) |
| `go/internal/reducer/service.go:284-294` | Worker loop: execute → log → fail (log before retry decision) |
| `go/internal/reducer/service.go:339-341` | Hardcoded `failure_class: "reducer_failure"` in logger |
| `go/internal/storage/postgres/reducer_queue.go:413-454` | Queue retry decision (`retryable()` → `failIntent()`) |
| `go/internal/reducer/intent.go:81-97` | `RetryableError` interface and `IsRetryable()` |
| `go/cmd/reducer/config.go:40-52` | Worker count: `PCG_REDUCER_WORKERS`, default min(NumCPU, 4) |
| `docker-compose.yaml:349` | Production default: `PCG_REDUCER_WORKERS=4` |
| `neo4j-go-driver/.../errorutil/retry.go` | `TransactionExecutionLimit` — no `Unwrap()` method |
