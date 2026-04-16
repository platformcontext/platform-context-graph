# ADR: Cross-Phase EntityNotFound Race Between Projector and Reducer

**Status:** Accepted — Claude and Codex independently converged on Option C + F

**Date:** 2026-04-16

## Context

The platform indexes 896 repositories through a pipeline of projector (canonical
graph writes) and reducer (materialization from facts). After commit `6e67151e`
(GroupExecutor for semantic entity atomicity), the 896-repo E2E test on the
remote instance (ubuntu@10.208.198.57) produces **1,275 reducer failures** out
of 10,249 total executions. Classified Neo4j evidence shows **1,061
`EntityNotFound`** errors and **220 `DeadlockDetected`** errors, with the small
count difference explained by multi-line log formatting in a handful of
entries.

These errors block the system from achieving zero-error indexing, which is the
acceptance criterion for production readiness.

### Constraints (non-negotiable)

1. **No procedural slowdowns** — no artificial delays, visibility windows, or
   sequential bottlenecks between projector and reducer.
2. **No race conditions** — eliminate the error path entirely.
3. **Accuracy first** — never silently drop data. If a current-generation
   intent fails, that failure MUST surface as an error.

## Error Evidence

### Deployment Data (2026-04-16, fresh `docker compose down -v` run)

| Metric | Value |
|--------|-------|
| Total reducer executions | ~10,249 |
| Succeeded | ~8,974 |
| Failed | 1,275 |
| Superseded (generation guard) | 0 |
| Repos projected | 896/896 |
| Error time window | 20:16–21:49 UTC (93 minutes) |

### Classified Error Breakdown

All 1,275 errors are Neo4j errors. There are exactly two error types:

| Neo4j Error Code | Semantic Entity | Code Call | Total | % |
|------------------|----------------|-----------|-------|---|
| `Neo.ClientError.Statement.EntityNotFound` | 990 | 71 | **1,061** | 83% |
| `Neo.TransientError.Transaction.DeadlockDetected` | 216 | 4 | **220** | 17% |
| **Total** | **1,206** | **75** | **1,281** | |

(The 6-count difference from the 1,275 log-line count is due to multi-line
error messages in a small number of log entries.)

### What the Neo4j Error Codes Mean

**`Neo.ClientError.Statement.EntityNotFound`** (`Unable to load NODE 4:...:NNN`):
The Cypher engine resolved a node via index lookup, obtained an internal node
ID, then another committed transaction deleted that node before the current
transaction could load it. This is a Neo4j MVCC artifact under read-committed
isolation: the node was valid when the index was read but gone by the time the
storage engine fetched the full record.

Example from logs:
```
write semantic entities: write semantic entities: Neo4jError:
Neo.ClientError.Statement.EntityNotFound (Unable to load NODE
4:1d852d49-e974-435c-bf22-a4df7a621769:5087.)
```

**`Neo.TransientError.Transaction.DeadlockDetected`**: Classic write-write
lock cycle. Two transactions (projector Phase A `DETACH DELETE` and reducer
`MERGE`) acquire locks on the same nodes in different order, and Neo4j kills
one to break the cycle.

### Why These Errors Are Terminal Today

Both error types are fundamentally transient — retrying after the projector
commits would succeed. However:

- `EntityNotFound` is classified as `ClientError` by Neo4j, NOT `TransientError`.
  The Neo4j Go driver does NOT auto-retry `ClientError` codes.
- The reducer handler wraps all Neo4j errors with plain `fmt.Errorf(...)`.
  The queue's `ReducerQueue.Fail()` only re-enqueues errors that implement
  `RetryableError` (checked via `reducer.IsRetryable()`). Plain wrapped errors
  do not satisfy this interface.
- Result: all 1,061 EntityNotFound errors and all 220 DeadlockDetected errors
  are treated as **permanent failures** — never retried.

### Top Error Repos

| Repo ID | Error Count |
|---------|-------------|
| r_c7dab3f7 | 105 |
| r_c5014438 | 77 |
| r_8e5b9f15 | 64 |
| r_a8862bc6 | 53 |

Errors occur **throughout the full 93-minute run timeline**, not concentrated
at the start or end. This rules out a startup-only ordering issue and confirms
sustained concurrent projector/reducer activity.

### How the Errors Manifest

**`semantic_entity_materialization` (1,206 errors):** The reducer's
`WriteSemanticEntities` runs `ExecuteGroup` with a retract statement followed
by upsert statements. Each upsert does `MATCH (f:File {path: row.file_path})`
to anchor semantic entities to File nodes. When the projector's Phase A
concurrently deletes that File node and commits, Neo4j's read-committed
isolation allows the MATCH to resolve the index entry but fail to load the
underlying node record, producing `Neo.ClientError.Statement.EntityNotFound`.
Lock contention between the reducer's MERGE and the projector's DETACH DELETE
produces `Neo.TransientError.Transaction.DeadlockDetected`.

**`code_call_materialization` (75 errors):** The reducer's Cypher does
`MATCH (source:Function|Class|File {uid: ...})` and
`MATCH (target:Function|Class|File {uid: ...})` to create CALLS/REFERENCES
edges. The same MVCC race applies: the projector deletes entity nodes
(Phase A) while the reducer tries to load them.

**Error origin is Neo4j, not application code.** The `EntityNotFound` string
in the logs comes from Neo4j's `Neo.ClientError.Statement.EntityNotFound`
error code, not from any application-level comparison of expected vs actual
writes. The reducer handlers wrap and propagate this Neo4j error via
`fmt.Errorf("write semantic entities: %w", err)`.

## Root Cause Analysis

### Two Distinct Race Windows

#### Race 1: Cross-Generation (SOLVED)

When a repository is re-indexed (new generation), the projector:
1. Activates the new generation in `ingestion_scopes.active_generation_id`
2. Runs Phase A: `DETACH DELETE` nodes where `generation_id <> $generation_id`
3. Creates new nodes for the new generation (Phases B-G)

If the reducer processes intents from the OLD generation after step 2, its
`MATCH` hits deleted nodes.

**Solution implemented:** Generation Guard (commit `6e67151e`). Before executing
any reducer intent, `Runtime.execute()` checks
`ingestion_scopes.active_generation_id` against the intent's generation. Stale
intents are acked as "superseded" without touching Neo4j.

**Result:** 0 superseded intents in the fresh-index run. This is correct —
a fresh `docker compose down -v` run has exactly one generation per repo, so
there are no stale generations to guard against. The generation guard is
necessary for production re-index scenarios but does not address the remaining
within-generation failures.

#### Race 2: Within-Generation (UNSOLVED — this ADR)

The projector and reducer run concurrently on the **same generation**. The
projector's canonical write (Phases A-G) and the reducer's materialization
execute in separate Neo4j transactions with no coordination.

**Race variant 1 — EntityNotFound (83% of errors):**

```
Projector Phase A tx: DELETE old Files → commits
                                           Reducer MATCH (f:File {path: ...})
                                             → index resolves → internal node ID
                                             → storage loads node → DELETED
                                             → Neo.ClientError.Statement.EntityNotFound ✗
Projector Phase D tx: MERGE new Files → commits
                                           (If retried now, would succeed ✓)
```

**Race variant 2 — DeadlockDetected (17% of errors):**

```
Projector: DETACH DELETE File F1           Reducer: MERGE entity → File F1
  → lock on F1, needs lock on E1             → lock on E1, needs lock on F1
  → DEADLOCK → Neo4j kills one transaction
```

**Why phases are not atomic:** `CanonicalNodeWriter.Write()` executes phases
A through G sequentially, but each `executor.Execute()` opens a separate Neo4j
session/transaction. There is NO single transaction wrapping all phases.

See: `go/internal/storage/neo4j/canonical_node_writer.go:64-74`

### Contributing Factors

#### 1. Projector canonical writes are non-atomic

`CanonicalNodeWriter.Write()` executes phases A-G in order, but each phase and
each Phase A retraction statement is a separate `Execute(...)` call. The
projector Neo4j executor opens a fresh Neo4j write session per call and does
not implement `GroupExecutor`, so there is no projector-side transaction that
hides intermediate state from the reducer.

This is the strongest same-generation race candidate on the current branch.

#### 2. Directory retract has NO generation filter

```cypher
-- go/internal/storage/neo4j/canonical_node_cypher.go:42-44
MATCH (d:Directory)
WHERE d.repo_id = $repo_id
DETACH DELETE d
```

All other Phase A retractions filter by `generation_id <> $generation_id`.
Directories unconditionally delete everything for the repo.

#### 3. Semantic entity retract has NO generation filter

```cypher
-- go/internal/storage/neo4j/semantic_entity.go:243-246
MATCH (n:Annotation|Typedef|TypeAlias|TypeAnnotation|Component|Module|
       ImplBlock|Protocol|ProtocolImplementation|Variable|Function)
WHERE n.repo_id IN $repo_ids
  AND n.evidence_source = $evidence_source
DETACH DELETE n
```

This is still too broad for future generation-aware cleanup semantics.
However, in the deployed reducer path the semantic entity writer already uses
`ExecuteGroup(...)` when the executor supports it, so retract plus upsert runs
atomically there. That makes this a weaker explanation for the same-generation
observation window than the projector's canonical writer.

Also note that semantic entity nodes do not currently store `generation_id`, so
adding a generation predicate here requires a schema/property change first.

#### 4. Projector enqueues reducer intents AFTER canonical write

```go
// go/internal/projector/runtime.go:122
if err := r.CanonicalWriter.Write(ctx, projection.canonical); err != nil { ... }

// go/internal/projector/runtime.go:173
intentResult, err := r.IntentWriter.Enqueue(ctx, projection.reducerIntents)
```

This ordering means reducer intents are enqueued AFTER the projector finishes
all canonical writes for the SAME repo. That weakens the simple "Repo X reducer
outran Repo X projector" timeline unless there are multiple projector workers,
another source of same-generation intents, or cross-repo references that depend
on nodes another scope is still rewriting.

The ordering is still relevant, but it does not by itself prove a same-repo
claim-before-write race.

#### 5. Reducer MATCH depends on nodes the projector creates

Code call upserts require both source AND target entity nodes to exist
(`MATCH (source:Function|Class|File {uid: ...})` + `MATCH (target:...)`).
Semantic entity upserts require File nodes (`MATCH (f:File {path: ...})`).
When the projector deletes these nodes (Phase A) and the reducer MATCHes them
mid-flight, Neo4j produces `EntityNotFound` (index resolves, node gone) or
a silent no-op (MATCH returns 0 rows). The classified errors are the former.

## Options Considered

### Option A: OPTIONAL MATCH (REJECTED)

Replace `MATCH (f:File ...)` with `OPTIONAL MATCH (f:File ...)` and skip rows
where the anchor is null.

**Why rejected:** Violates constraint #3 (accuracy first). OPTIONAL MATCH makes
stale-generation races and current-generation data integrity bugs produce the
same silent no-op. There is no way to distinguish "expected skip" from "data
loss." Even with the generation guard, OPTIONAL MATCH hides within-generation
bugs where the projector failed to create a node it should have created.

### Option B: Generation Guard Only (CURRENT STATE — INSUFFICIENT)

Check `ingestion_scopes.active_generation_id` before executing reducer intents.
Skip stale-generation intents as "superseded."

**What it solves:** Cross-generation race (re-index scenarios).

**What it does NOT solve:** Within-generation race. On a fresh index, every
intent has the current generation, so the guard passes all intents through.

### Option C: Atomic Canonical Write Transaction

Wrap all Phase A-G statements in a single Neo4j transaction so the reducer
never observes intermediate state (nodes deleted but not yet recreated).

**Pros:**
- Eliminates the within-generation window entirely
- Clean semantic: the graph transitions atomically from old state to new state
- No changes needed in the reducer

**Cons:**
- Large transactions for repos with many entities (biggest repo has 105 errors,
  likely thousands of nodes) — may hit Neo4j transaction memory limits
- Requires Neo4j driver transaction API changes in the executor layer
- Phase A retractions + Phase D-G creations in one transaction could be slow

**Assessment:** This is now the primary fix candidate. The reducer already has
transaction-group support in its Neo4j wiring; the missing piece is projector
support for grouped canonical writes.

### Option D: Reducer Intent Delay / Availability Window

Set `available_at` on reducer intents to `enqueued_at + N seconds`, giving the
projector time to complete canonical writes before the reducer claims intents.

**Pros:**
- Simple to implement (one-line change in intent enqueue)
- No Neo4j changes

**Cons:**
- Violates constraint #1 (no procedural slowdowns)
- Fragile: the delay must be longer than the slowest canonical write, which
  varies by repo size
- Adds latency to every reducer intent, even when no race exists

**Assessment:** Rejected per user rules.

### Option E: Projector-Reducer Ordering via Ready Flag

Add a `canonical_write_completed` flag to `scope_generations` or
`ingestion_scopes`. The projector sets it after Phase G completes. The reducer
checks it before executing intents for that scope+generation.

**Pros:**
- Precise: reducer waits only when canonical write is actually in progress
- No artificial delay — reducer proceeds immediately when flag is set
- Single Postgres column, indexed lookup

**Cons:**
- Adds a coordination point between projector and reducer (tight coupling)
- Reducer must re-enqueue or sleep-and-retry intents when flag is not set
- Edge case: if projector crashes between Phase A and setting the flag, intents
  are permanently blocked

**Assessment:** Viable but introduces coupling. Needs a timeout/fallback for
the crash case.

### Option F: Explicit Retryable Reducer Errors (Required Complement)

Wrap Neo4j `EntityNotFound` and `DeadlockDetected` errors from reducer
handlers in a type implementing `RetryableError` so the queue re-enqueues the
work item with bounded backoff.

**Evidence that this is needed:** All 1,281 errors in the deployment are
currently terminal. The reducer handlers wrap Neo4j errors with plain
`fmt.Errorf(...)`. The queue's `ReducerQueue.Fail()` checks
`reducer.IsRetryable(cause)` before re-enqueuing — plain wrapped errors do
not satisfy `RetryableError`, so every failure is permanent.

Critically, `Neo.ClientError.Statement.EntityNotFound` is a `ClientError` in
the Neo4j error taxonomy, NOT a `TransientError`. The Neo4j Go driver does NOT
auto-retry `ClientError` codes. Without explicit typing, even the driver's
built-in retry loop does not help.

Scope note: this should be applied narrowly to the reducer materialization
paths where classified evidence shows the errors are caused by concurrent
projector/reducer access to the same graph nodes. It should not become a
blanket policy that retries every future `EntityNotFound` regardless of domain
or context.

**Pros:**
- Converts 1,281 terminal failures into bounded retries
- Retries succeed once the projector commits (errors are fundamentally
  transient)
- Reuses the existing queue retry machinery (`RetryDelay`, `MaxAttempts`)
- Required safety net even after Option C — protects against edge cases,
  large repos exceeding transaction memory, and rollout windows

**Cons:**
- Requires identifying which Neo4j error codes should be retryable
  (EntityNotFound, DeadlockDetected — possibly others)
- Must be scoped carefully. An `EntityNotFound` caused by a genuine data
  integrity bug should still surface after bounded retries instead of being
  normalized away as harmless
- Retry attempts consume Neo4j round-trips that produce nothing
- Does not eliminate the race — tolerates it with bounded cost

**Assessment:** Required complement to Option C. Without Option F, any residual
concurrent-access errors remain terminal. Implementation should be small and
targeted: a wrapper error type that implements `Retryable() bool` for the
known concurrent reducer paths and specific Neo4j error codes evidenced here.

### Option G: Generation-Scoped Cleanup For Directory And Semantic Retract

Fix the two missing generation-scoping gaps, but treat this as supporting
cleanup rather than the main race fix.

```cypher
-- Proposed fix for semantic entity retract:
MATCH (n:Annotation|Typedef|...|Function)
WHERE n.repo_id IN $repo_ids
  AND n.evidence_source = $evidence_source
  AND n.generation_id <> $generation_id
DETACH DELETE n
```

```cypher
-- Proposed fix for directory retract:
MATCH (d:Directory)
WHERE d.repo_id = $repo_id
  AND d.generation_id <> $generation_id
DETACH DELETE d
```

**Pros:**
- Retractions only remove nodes from OLD generations, not the current one
- Makes cleanup semantics consistent across node families
- Reduces the chance that broad retracts amplify another race

**Cons:**
- Directory nodes currently lack `generation_id` property — requires schema
  change and projector update to set it
- Semantic entity nodes also currently lack `generation_id`, so the same schema
  change is required there before the proposed predicate is valid
- Does not eliminate the projector's same-generation observation window by
  itself

**Assessment:** Good cleanup but not the primary fix. The projector transaction
boundary is the main issue to address first.

## Recommendation

The classified error evidence (1,061 EntityNotFound + 220 DeadlockDetected)
confirms that projector and reducer Neo4j transactions operate on the same
nodes concurrently, and that ALL resulting errors are treated as terminal
failures today.

**Primary fix (Option C + F together):**

1. **Option C — Atomic projector canonical writes.** Wrap Phase A through G
   (or at minimum Phase A through Phase E) in a single Neo4j transaction via
   `ExecuteGroup`. This eliminates the observation window: the reducer either
   sees old-generation nodes or new-generation nodes, never the intermediate
   deleted-but-not-recreated state. The reducer already has `ExecuteGroup`
   support; the projector needs it added.
   - Eliminates the 1,061 EntityNotFound errors (no stale internal node IDs)
   - Reduces the 220 DeadlockDetected errors (fewer concurrent transactions,
     shorter lock windows)

2. **Option F — Type Neo4j errors as RetryableError.** Wrap
   `Neo.ClientError.Statement.EntityNotFound` and
   `Neo.TransientError.Transaction.DeadlockDetected` errors from reducer
   handlers in a type implementing `RetryableError`. This ensures any residual
   races (e.g., during Option C rollout or edge cases with very large repos
   that exceed transaction memory limits) are retried instead of terminally
   failed.
   - Safety net: converts 1,281 terminal failures into bounded retries
   - Required regardless of Option C because Neo4j `ClientError` codes are
     NOT auto-retried by the driver

**Supporting cleanup (Option G):** Add `generation_id` to Directory and
semantic entity nodes, then tighten those retracts to `generation_id <> current
generation`. This improves correctness and reduces over-broad cleanup but is
not the primary fix.

**Already in place:** Option B — generation guard for cross-generation races.

**Explicitly rejected:** Option A (OPTIONAL MATCH) and Option D (artificial
delays).

## Decision

**Accepted.** Claude and Codex independently converged on the same fix:

1. **Option C** — Atomic projector canonical writes (primary fix, eliminates
   the observation window)
2. **Option F** — RetryableError typing for Neo4j EntityNotFound and
   DeadlockDetected in reducer handlers (required safety net, scoped narrowly
   to evidenced concurrent-access paths)
3. **Option G** — Generation-scoped directory and semantic entity retracts
   (supporting cleanup, not the primary fix)
4. **Option B** — Generation guard already in place for cross-generation races

Option F is required regardless of Option C because
`Neo.ClientError.Statement.EntityNotFound` is a `ClientError` that the Neo4j
driver does not auto-retry, and all 1,281 current errors are terminal.

**Open investigation:** Factor 4 (projector enqueues AFTER canonical write)
creates a paradox with same-repo errors. Verify whether concurrent same-repo
projector workers exist in bootstrap-index during implementation.

## Key Source Files

| File | Relevance |
|------|-----------|
| `go/internal/storage/neo4j/canonical_node_writer.go` | Phase A-G execution, non-atomic transactions |
| `go/cmd/projector/runtime_wiring.go` | Projector executor opens a new write session per statement; no grouped transaction support |
| `go/internal/storage/neo4j/canonical_node_cypher.go` | All retraction and upsert Cypher templates |
| `go/internal/storage/neo4j/semantic_entity.go:243-246` | Semantic entity retract WITHOUT generation filter |
| `go/internal/storage/neo4j/semantic_entity.go:269-375` | Semantic entity writer uses grouped transaction execution when executor supports `GroupExecutor` |
| `go/cmd/reducer/neo4j_wiring.go` | Reducer executor implements `ExecuteGroup` via `session.ExecuteWrite(...)` |
| `go/internal/storage/neo4j/canonical.go:155-177` | Code call upsert Cypher with dual MATCH |
| `go/internal/projector/runtime.go:122,173` | Canonical write BEFORE intent enqueue ordering |
| `go/internal/reducer/runtime.go` | Generation guard in `execute()` |
| `go/internal/reducer/intent.go` | Retry only applies to errors that implement `RetryableError` |
| `go/internal/storage/postgres/reducer_queue.go` | Queue retry behavior and terminal failure behavior |

## Implementation Guide

### Option C: Atomic Projector Canonical Writes

**The gap:** The projector's Neo4j executor only implements `Execute()` (one
statement per session). It does NOT implement `GroupExecutor.ExecuteGroup()`.
The reducer already has both.

**Projector executor (needs `ExecuteGroup`):**

```go
// go/cmd/projector/runtime_wiring.go:93-117
type projectorNeo4jExecutor struct {
    Driver       neo4jdriver.DriverWithContext
    DatabaseName string
}

// CURRENT: only Execute() — opens a new session per statement
func (e projectorNeo4jExecutor) Execute(ctx context.Context, statement sourceneo4j.Statement) error {
    session := e.Driver.NewSession(ctx, neo4jdriver.SessionConfig{...})
    defer session.Close(ctx)
    result, err := session.Run(ctx, statement.Cypher, statement.Parameters)
    ...
}

// MISSING: ExecuteGroup() — needs to be added
```

**Reducer executor (reference implementation to copy):**

```go
// go/cmd/reducer/neo4j_wiring.go:82-109
func (r neo4jSessionRunner) RunCypherGroup(ctx context.Context, stmts []sourceneo4j.Statement) error {
    session := r.Driver.NewSession(ctx, neo4jdriver.SessionConfig{
        AccessMode:   neo4jdriver.AccessModeWrite,
        DatabaseName: r.DatabaseName,
    })
    defer session.Close(ctx)

    _, err := session.ExecuteWrite(ctx, func(tx neo4jdriver.ManagedTransaction) (any, error) {
        for _, stmt := range stmts {
            result, runErr := tx.Run(ctx, stmt.Cypher, stmt.Parameters)
            if runErr != nil { return nil, runErr }
            if _, consumeErr := result.Consume(ctx); consumeErr != nil { return nil, consumeErr }
        }
        return nil, nil
    })
    return err
}
```

**CanonicalNodeWriter (needs to use `ExecuteGroup` when available):**

```go
// go/internal/storage/neo4j/canonical_node_writer.go:46-74
// CURRENT: calls executor.Execute() per phase
// CHANGE: collect all Statement structs across all phases, then:
if ge, ok := w.executor.(GroupExecutor); ok {
    return ge.ExecuteGroup(ctx, allStatements)
}
// fallback: sequential Execute() calls (existing behavior)
```

**Bootstrap-index executor (same gap as projector):**

```go
// go/cmd/bootstrap-index/wiring.go:149-173
type bootstrapNeo4jExecutor struct { ... }
// Only has Execute(), needs ExecuteGroup() added
// Also wraps with RetryingExecutor — verify retry + group interaction
```

**Key interfaces:**

```go
// go/internal/storage/neo4j/writer.go:68-78
type Executor interface {
    Execute(context.Context, Statement) error
}

type GroupExecutor interface {
    ExecuteGroup(ctx context.Context, stmts []Statement) error
}
```

The `CanonicalNodeWriter` already holds an `Executor`. It should type-assert
to `GroupExecutor` (same pattern as `semantic_entity.go:363`). No interface
changes needed.

### Option F: RetryableError Typing

**Existing retry infrastructure:**

```go
// go/internal/reducer/intent.go:81-96
type RetryableError interface {
    error
    Retryable() bool
}

func IsRetryable(err error) bool {
    var retryable RetryableError
    if !errors.As(err, &retryable) { return false }
    return retryable.Retryable()
}
```

```go
// go/internal/storage/postgres/reducer_queue.go:413-414,434
func (q ReducerQueue) retryable(cause error, attemptCount int) bool {
    return reducer.IsRetryable(cause) && attemptCount < q.maxAttempts()
}
// Called in Fail() — if retryable, re-enqueue; else terminal
```

**What to add:** A new error wrapper in `go/internal/storage/neo4j/` or
`go/internal/reducer/` that:

1. Checks whether the wrapped error contains `Neo.ClientError.Statement.EntityNotFound`
   or `Neo.TransientError.Transaction.DeadlockDetected` (parse the Neo4j error
   code string)
2. Implements `Retryable() bool` returning `true` for those codes
3. Is applied in the semantic entity writer and code call edge writer error
   paths (or in the `InstrumentedExecutor` layer that wraps all Neo4j calls)

**Scoping rule (from Codex review):** Apply narrowly to reducer materialization
paths only. Do NOT make this a blanket retry for all `EntityNotFound` errors.
After `MaxAttempts` exhausted, the error must still surface as terminal.

**Neo4j Go driver error inspection:**

```go
import "github.com/neo4j/neo4j-go-driver/v5/neo4j"

// The driver exposes neo4j.IsNeo4jError() and the error type has a Code field
var neo4jErr *neo4j.Neo4jError
if errors.As(err, &neo4jErr) {
    switch neo4jErr.Code {
    case "Neo.ClientError.Statement.EntityNotFound":
        // wrap as retryable
    case "Neo.TransientError.Transaction.DeadlockDetected":
        // wrap as retryable (driver may already retry these internally
        // via session.ExecuteWrite, but session.Run does NOT)
    }
}
```

### Option G: Generation-Scoped Retracts (Supporting Cleanup)

**Directory retract — add `generation_id` filter:**

```cypher
-- go/internal/storage/neo4j/canonical_node_cypher.go:42-44
-- CURRENT:
MATCH (d:Directory) WHERE d.repo_id = $repo_id DETACH DELETE d

-- PROPOSED (requires adding generation_id to Directory nodes first):
MATCH (d:Directory)
WHERE d.repo_id = $repo_id AND d.generation_id <> $generation_id
DETACH DELETE d
```

**Prerequisite:** Phase C directory MERGE must SET `d.generation_id`:

```cypher
-- go/internal/storage/neo4j/canonical_node_cypher.go:61-65
-- CURRENT:
MERGE (d:Directory {path: row.path})
SET d.name = row.name, d.repo_id = row.repo_id

-- PROPOSED:
MERGE (d:Directory {path: row.path})
SET d.name = row.name, d.repo_id = row.repo_id, d.generation_id = row.generation_id
```

**Semantic entity retract:** Same pattern but requires adding `generation_id`
to all 11 semantic entity upsert Cypher templates. Lower priority since the
reducer already uses `ExecuteGroup` for atomic retract+upsert.

### Verification Plan

```bash
# After Option C implementation:
ssh ubuntu@10.208.198.57
cd /home/ubuntu/personal-repos/platform-context-graph
git pull && docker compose down -v && docker compose up --build -d

# Monitor for zero errors:
docker compose logs -f resolution-engine 2>&1 | \
  rg '"status":"failed"' --count

# Expected: 0 EntityNotFound, 0 DeadlockDetected
# The generation guard should still show 0 superseded (fresh run)

# After Option F implementation (with or without C):
# Any residual errors should show failure_class="reducer_retryable"
# and be retried up to MaxAttempts before becoming terminal
docker compose logs resolution-engine 2>&1 | \
  rg 'reducer_retryable' --count
```

## Appendices

Cypher templates, raw log samples, error classification data, and terminal
error code paths are in the companion evidence file:

[Cross-Phase EntityNotFound Race — Evidence Appendix](2026-04-16-cross-phase-entity-not-found-race-evidence.md)
