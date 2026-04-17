# ADR: Semantic Entity Materialization Queue Throughput

**Status:** Proposed
**Date:** 2026-04-17

## Problem Statement

The reducer queue is bottlenecked by `semantic_entity_materialization`. It
generates **58x more intents** than every other domain because it creates
one intent per entity instead of one intent per repo. This causes:

1. **Queue bloat:** 51,806 semantic entity intents vs 889 for every other
   domain (6 domains × 889 = 5,334 total non-semantic intents)
2. **Estimated drain time:** ~4.1 hours at current throughput for semantic
   entities alone
3. **Resource contention:** Postgres at 84% CPU from queue churn, Neo4j at
   361% CPU from concurrent writes, while bootstrap-index is still
   ingesting at 194% CPU and 7.6 GiB RAM

### Production Evidence (2026-04-17, 896-repo E2E run)

| Domain | Pending | Succeeded | Total | Per Repo | Avg Duration |
|--------|---------|-----------|-------|----------|-------------|
| **semantic_entity** | **49,203** | **2,558** | **51,806** | **~58** | **17.72s** |
| code_call | 617 | 270 | 889 | 1 | 6.18s |
| sql_relationship | 618 | 269 | 889 | 1 | 7.11s |
| inheritance | 617 | 272 | 889 | 1 | 3.98s |
| deployment_mapping | 617 | 272 | 889 | 1 | 4.07s |
| workload_identity | 618 | 271 | 889 | 1 | 4.23s |
| workload_materialization | 618 | 271 | 889 | 1 | 4.16s |

Throughput: 3.3 items/sec across 4 workers. All domains compete for the
same 4 workers via FIFO ordering, so the 51K semantic entity backlog
starves the other 6 domains.

### Resource Snapshot

| Service | CPU | Memory | Notes |
|---------|-----|--------|-------|
| bootstrap-index | 194% | 7.6 GiB | Still parsing large repos (wordpress, youboat-php) |
| neo4j | 361% | 6.7 GiB | Concurrent canonical writes + reducer edge/entity writes |
| postgres | 84% | 5.9 GiB | Queue churn: 57K rows with FOR UPDATE SKIP LOCKED polling |
| resolution-engine | 54% | 138 MiB | 4 workers, 45 in-flight — not the bottleneck |

## Root Cause Analysis

### The Intent Granularity Gap

Every other reducer domain generates **one intent per repo**:

```go
// go/internal/projector/runtime.go:225 — generic path
intents = append(intents, buildReducerIntent(fact))
```

Semantic entity generates **one intent per entity**:

```go
// go/internal/projector/semantic_entity_intents.go:23-68
func buildSemanticEntityReducerIntent(fact facts.Envelope) (ReducerIntent, bool) {
    // ...
    return ReducerIntent{
        ScopeID:      fact.ScopeID,       // per-entity scope
        GenerationID: fact.GenerationID,
        Domain:       reducer.DomainSemanticEntityMaterialization,
        EntityKey:    entityID,            // per-entity key
        // ...
    }, true
}
```

Called from `buildProjection()` at `runtime.go:222-223`:

```go
if intent, ok := buildSemanticEntityReducerIntent(fact); ok {
    intents = append(intents, intent)
}
```

Each `content_entity` fact triggers a separate intent. A repo with 100
entities generates 100 intents, each requiring its own
claim-execute-ack cycle.

### The Overhead Per Intent

Each semantic entity intent requires:

| Phase | Postgres | Neo4j | Notes |
|-------|----------|-------|-------|
| Claim | 1 round-trip | 0 | `FOR UPDATE SKIP LOCKED` over 57K rows |
| Load facts | 1 round-trip | 0 | `ListFacts(ctx, scopeID, generationID)` |
| Write entities | 0 | 1 round-trip | Retract + upsert via `GroupExecutor` |
| Ack | 1 round-trip | 0 | Single UPDATE |

**Total: 3 Postgres + 1 Neo4j round-trip per entity.**

For 51,806 entities: **155,418 Postgres round-trips + 51,806 Neo4j
round-trips.** If these were batched per-repo (889 intents): **2,667
Postgres + 889 Neo4j round-trips** — a 58x reduction.

### The Write Path Already Supports Batching

`WriteSemanticEntities()` (`semantic_entity.go:269-376`) is designed for
multi-entity writes:

1. Groups rows by label into 11 label buckets
   (`semantic_entity.go:286-298`)
2. Batches each label via `UNWIND $rows` at 500 rows per batch
   (`semantic_entity.go:317-346`)
3. Executes ALL statements atomically via `GroupExecutor.ExecuteGroup()`
   (`semantic_entity.go:363-373`)

The UNWIND Cypher templates (`semantic_entity.go:14-237`) accept arbitrary
row counts. The write path is not the bottleneck — intent granularity is.

### The Fact Loading Path Already Supports Per-Repo Loads

`SemanticEntityMaterializationHandler.Handle()` calls:

```go
// go/internal/reducer/semantic_entity_materialization.go:71
envelopes, err := h.FactLoader.ListFacts(ctx, intent.ScopeID, intent.GenerationID)
```

`ListFacts` queries by `scope_id` and `generation_id`. If the intent's
`ScopeID` were the repository scope (not the entity scope), this would
return ALL entity facts for that repo in a single query — which
`ExtractSemanticEntityRows()` already handles (it filters by entity type
and validates fields).

### Why Per-Entity Intents Existed

The original design used per-entity granularity for:

1. **Fine-grained retry:** If one entity fails, only that entity is
   retried, not the entire repo.
2. **Incremental updates:** When a single file changes, only affected
   entities are re-materialized.
3. **Parallelism:** Multiple workers can process different entities from
   the same repo concurrently.

These motivations are valid for incremental updates in production. However,
for bulk indexing (bootstrap, re-index), they create a 58x overhead that
dominates the queue.

### Queue Starvation

The claim query orders by `updated_at ASC` with no domain filtering:

```sql
-- go/internal/storage/postgres/reducer_queue.go:30-42
WHERE stage = 'reducer'
  AND status IN ('pending', 'retrying')
  AND (visible_at IS NULL OR visible_at <= $1)
  AND (claim_until IS NULL OR claim_until <= $1)
  AND ($2 = '' OR domain = $2)
ORDER BY updated_at ASC, work_item_id ASC
```

The `$2` parameter is always `""` (`reducer_queue_batch.go:70`), so no
domain filtering is applied. With 51K semantic entity intents interleaved
with 5K other-domain intents, workers spend ~90% of their time on
semantic entities while code_call, inheritance, and other domains wait.

## Impact at Scale

| Scenario | Semantic Intents | Drain Time (4 workers) | Neo4j Round-Trips |
|----------|-----------------|----------------------|-------------------|
| 896 repos (current) | 51,806 | ~4.1 hours | 51,806 |
| 896 repos (per-repo) | 889 | ~4.5 minutes | 889 |
| 5,000 repos | ~290,000 | ~23 hours | 290,000 |
| 5,000 repos (per-repo) | 5,000 | ~25 minutes | 5,000 |

Per-entity intent granularity scales linearly with total entity count
across all repos. Per-repo scales linearly with repo count only.

## Options

### Option A: Per-Repo Intent Consolidation (Recommended)

Change `buildSemanticEntityReducerIntent()` to emit one intent per repo
instead of one per entity. The handler loads all entity facts for the repo
and writes them in a single `WriteSemanticEntities()` call.

**Intent generation change:**

```go
// Replace per-entity intent builder with per-repo aggregation
// in go/internal/projector/runtime.go buildProjection()

// Collect unique repo scopes for semantic entity facts
semanticRepoScopes := map[string]projector.ReducerIntent{}
for _, fact := range entityFacts {
    repoID := payloadString(fact.Payload, "repo_id")
    if _, seen := semanticRepoScopes[repoID]; !seen {
        semanticRepoScopes[repoID] = ReducerIntent{
            ScopeID:      fact.ScopeID,
            GenerationID: fact.GenerationID,
            Domain:       reducer.DomainSemanticEntityMaterialization,
            EntityKey:    "repo:" + repoID,
            Reason:       "semantic entity follow-up for repository",
        }
    }
}
for _, intent := range semanticRepoScopes {
    intents = append(intents, intent)
}
```

**Handler change:**

```go
// go/internal/reducer/semantic_entity_materialization.go:71
// ListFacts already returns all facts for the scope/generation.
// ExtractSemanticEntityRows already handles multi-entity extraction.
// No handler changes needed if ScopeID maps to the repo scope.
```

**Pros:**
- 58x fewer intents (51,806 → 889)
- 58x fewer Postgres claim/ack round-trips
- 58x fewer Neo4j sessions
- Larger UNWIND batches → better Neo4j throughput
- Reduces deadlock surface (fewer concurrent writers per repo)
- No changes to the Neo4j write path
- No changes to the fact loading path

**Cons:**
- **Loses per-entity retry granularity:** If one entity in a batch of 100
  fails, the entire repo is retried. All 100 entities are re-processed.
  At current error rates (0.006%), this is acceptable.
- **Larger transactions:** A repo with 5,000 entities generates one large
  Neo4j transaction instead of 5,000 small ones. This increases
  per-transaction memory and lock duration. Neo4j's default transaction
  memory limit is 256MB — a 5,000-entity UNWIND with 11 labels is well
  within this.
- **Loses per-entity parallelism:** Two workers can't process entities
  from the same repo concurrently. Since the claim query has no
  per-repo affinity today, this parallelism was already incidental.
- **Incremental updates must still work:** When a single file changes in
  production, the projector should emit intents for just the affected
  entities, not re-materialize the entire repo. This requires the
  per-repo path to be used for bulk operations (bootstrap/re-index) and
  the per-entity path preserved for incremental updates.

**Risk mitigation for large repos:**

The largest repos in the fleet have ~5,000 entities. A single
`WriteSemanticEntities()` call with 5,000 entities generates:
- 1 retract statement
- ~10-20 UNWIND batches (500 entities per batch per label)
- All executed atomically via `GroupExecutor`

This is comparable to the canonical node writer's Phase A-G atomic write,
which already handles repos of this size. If a repo exceeds Neo4j
transaction memory limits, the handler can fall back to chunked execution
(e.g., 1000 entities per sub-batch) with `retryable` error handling on
each chunk.

### Option B: Domain-Priority Claiming

Add domain priority to the claim query so non-semantic domains are
processed first, preventing starvation.

**Claim query change:**

```sql
ORDER BY
    CASE WHEN domain = 'semantic_entity_materialization' THEN 1 ELSE 0 END,
    updated_at ASC, work_item_id ASC
```

Or use the existing `$2` domain filter parameter to claim non-semantic
domains first, then semantic:

```go
// First pass: claim non-semantic
intents, _ := q.ClaimBatch(ctx, limit, "!semantic_entity_materialization")
// Second pass: claim semantic (if workers still idle)
intents, _ = q.ClaimBatch(ctx, limit, "semantic_entity_materialization")
```

**Pros:**
- No intent generation changes
- Other domains complete in minutes instead of waiting hours
- Simple SQL change

**Cons:**
- Does not reduce the 51K intent overhead
- Does not reduce Postgres/Neo4j round-trips
- Semantic entities still take 4+ hours
- Masks the underlying problem

**Assessment:** Useful as a complement to Option A, not as a standalone
fix. Prevents starvation regardless of queue composition.

### Option C: Batch Intent Processing

Keep per-entity intents but process them in batches. Instead of claiming
one intent and executing it, claim N intents for the same repo/domain and
execute them together.

**Service change:**

```go
// After ClaimBatch(), group intents by (domain, repo_id)
groups := groupIntentsByDomainAndRepo(claimed)
for _, group := range groups {
    // Execute all intents in group as one handler call
    result, err := s.Executor.ExecuteBatch(ctx, group)
}
```

**Pros:**
- Preserves per-entity retry granularity
- Reduces Neo4j round-trips (batch N entities per write)
- No intent generation changes

**Cons:**
- Requires new `ExecuteBatch` on every handler — significant refactor
- Claim query returns FIFO items — may not batch well across repos
- The batch claim query would need repo-affinity (`GROUP BY repo_id`) to
  be effective, requiring a new SQL query
- Complex: coordination between claim, grouping, execution, and ack/fail
- Per-entity intents still consume 51K rows in `fact_work_items` — table
  bloat remains

**Assessment:** High implementation complexity for moderate benefit.
Option A achieves the same result with simpler changes.

### Option D: Shared Projection Path for Semantic Entities

Move semantic entity materialization from the per-intent reducer queue to
the `SharedProjectionRunner` path, which already handles code_calls,
inheritance, sql_relationships, and other cross-domain materializations
via partition-based polling.

**How SharedProjectionRunner works:**
(`go/internal/reducer/shared_projection_runner.go:116-254`)

- Polls `shared_projection_intents` table (not `fact_work_items`)
- Processes intents by partition (domain × partition key)
- Uses lease-based concurrency (one worker per partition)
- Batch limit: 100 per partition per cycle
- Already handles 6 domains

**Pros:**
- Decouples semantic entity processing from the main reducer queue
- Partition-based processing naturally groups by domain
- Main queue drains faster (only 5,334 non-semantic intents)

**Cons:**
- Requires rewriting semantic entity intent generation to target
  `shared_projection_intents` instead of `fact_work_items`
- SharedProjection uses a different intent schema
  (`SharedProjectionIntentRow` with `Payload map[string]any`)
- The semantic entity handler would need adapting to the shared projection
  interface
- Significant refactor across projector + reducer
- Doesn't address the per-entity granularity — still 51K intents, just in
  a different table

**Assessment:** Wrong abstraction. SharedProjection is designed for
cross-domain edge materialization (relationships between entities). Semantic
entity materialization is per-entity node/property writes — it belongs in
the reducer queue, just with better granularity.

### Option E: Dual-Mode Intent Generation

Keep per-entity intents for incremental updates but switch to per-repo
intents for bulk operations (bootstrap, re-index).

**Mechanism:** The projector detects whether it's processing a fresh scope
(bootstrap/re-index) vs an incremental update (single file change) and
emits intents accordingly.

```go
// go/internal/projector/runtime.go buildProjection()
if isFullReindex(projection) {
    // Emit one intent per repo (bulk mode)
    intents = append(intents, buildRepoSemanticEntityIntent(facts))
} else {
    // Emit one intent per affected entity (incremental mode)
    for _, fact := range entityFacts {
        if intent, ok := buildSemanticEntityReducerIntent(fact); ok {
            intents = append(intents, intent)
        }
    }
}
```

**Pros:**
- Best of both worlds: bulk efficiency + incremental precision
- Preserves per-entity retry for production incremental updates
- Bulk path (bootstrap/re-index) drops from 51K to 889 intents

**Cons:**
- Two code paths to maintain and test
- The handler must handle both single-entity and multi-entity intents
- Detection of "full re-index" vs "incremental" requires heuristics or
  an explicit flag in the fact metadata
- More complex to reason about correctness

**Assessment:** Over-engineered for the current state. Option A with
per-repo intents is sufficient — the retry cost of re-processing a full
repo on failure is negligible at 0.006% error rate. If incremental
precision becomes important in production, Option E can be introduced
later as a refinement.

## Recommendation

**Option A (per-repo intent consolidation)** as the primary fix, with
**Option B (domain-priority claiming)** as a complement.

### Why Option A

The numbers are stark:

| Metric | Per-Entity (current) | Per-Repo (Option A) | Reduction |
|--------|---------------------|--------------------|-----------| 
| Queue items | 51,806 | 889 | **58x** |
| Postgres claim round-trips | 51,806 | 889 | **58x** |
| Neo4j sessions | 51,806 | 889 | **58x** |
| Estimated drain time | ~4.1 hours | ~4.5 minutes | **55x** |
| Neo4j deadlock surface | 51K concurrent txns | 889 concurrent txns | **58x** |

The write path (`WriteSemanticEntities`) already handles multi-entity
batches with UNWIND + GroupExecutor. The fact loader (`ListFacts`) already
supports scope-level queries. No changes needed in either layer.

### Why Option B as complement

Domain-priority claiming prevents semantic entity dominance from starving
other domains regardless of intent granularity. A simple `ORDER BY`
change or two-pass claim gives operators control without code changes.

### Trade-off: Per-Entity Retry Granularity

The main trade-off is losing per-entity retry. If one entity in a 100-
entity repo fails, all 100 are retried. Given:

- Current error rate: 0.006% (2 deadlocks / 35K intents)
- All failures are transient (deadlocks, not data corruption)
- A retry re-processes the full entity set — idempotent via MERGE

The cost of over-retrying is a single extra Neo4j transaction per failed
repo, not per failed entity. At 0.006%, this affects <1 repo per run.

### What NOT to change

- **The Neo4j write path:** `WriteSemanticEntities()` is well-designed
  with UNWIND batching and GroupExecutor atomicity. Leave it alone.
- **The claim/ack batch mechanics:** `ClaimBatch` and `AckBatch` are
  already efficient. The overhead is per-intent, not per-batch.
- **The reducer worker count:** 4 workers is appropriate. Adding workers
  increases Neo4j contention without addressing the 58x intent overhead.
- **The SharedProjectionRunner:** It's the wrong abstraction for semantic
  entity node writes.

## Implementation Guide

### Phase 1: Per-Repo Intent Consolidation

**File: `go/internal/projector/semantic_entity_intents.go`**

Replace `buildSemanticEntityReducerIntent()` (per-entity) with
`buildSemanticEntityRepoIntent()` (per-repo). The new function
deduplicates by `(scope_id, generation_id, repo_id)` to emit one intent
per repo.

**File: `go/internal/projector/runtime.go`**

In `buildProjection()`, replace the per-entity loop (lines 222-224) with
per-repo aggregation. Collect all `content_entity` facts, deduplicate by
repo, emit one intent per repo.

**File: `go/internal/reducer/semantic_entity_materialization.go`**

Verify the handler works with per-repo intents. `ListFacts` returns all
facts for the scope, `ExtractSemanticEntityRows` filters by entity type.
If the scope is per-repo, this naturally returns all entities for that
repo. Minimal or no handler changes expected.

### Phase 2: Domain-Priority Claiming (Optional)

**File: `go/internal/storage/postgres/reducer_queue.go`**

Modify `claimReducerWorkQuery` and `claimReducerWorkBatchQuery` to
prioritize non-semantic domains:

```sql
ORDER BY
    CASE WHEN domain = 'semantic_entity_materialization' THEN 1 ELSE 0 END,
    updated_at ASC, work_item_id ASC
```

Or expose the existing `$2` domain filter parameter and implement
two-pass claiming in the service layer.

### Phase 3: Monitoring

Add the following telemetry to track the improvement:

- `pcg_dp_reducer_queue_depth` gauge by domain — already exists; verify
  it breaks down by domain
- `pcg_dp_reducer_intent_batch_size` histogram — entities per intent for
  semantic entity domain
- `pcg_dp_reducer_drain_rate` counter — intents processed per minute by
  domain

## Verification Plan

### Unit Tests

```bash
cd go && go test ./internal/projector/... -count=1 -run "SemanticEntity|Intent"
cd go && go test ./internal/reducer/... -count=1 -run "SemanticEntity"
cd go && go test ./internal/storage/neo4j/... -count=1 -run "SemanticEntity"
```

### E2E Validation (remote instance)

```bash
ssh ubuntu@10.208.198.57
cd /home/ubuntu/personal-repos/platform-context-graph
git pull && docker compose down -v && docker compose up --build -d

# After bootstrap completes, check queue composition:
docker compose exec postgres psql -U pcg -d platform_context_graph \
  -c "SELECT domain, status, COUNT(*) FROM fact_work_items
      WHERE stage = 'reducer' GROUP BY domain, status ORDER BY domain;"

# Expected: semantic_entity_materialization should show ~889 pending (1 per repo)
# instead of ~51,806

# Monitor drain time:
watch -n 10 'docker compose exec -T postgres psql -U pcg \
  -d platform_context_graph -c "SELECT status, COUNT(*) FROM fact_work_items
  WHERE stage = '\''reducer'\'' GROUP BY status;"'

# Expected: full queue drain in ~30-45 minutes instead of ~4+ hours
```

### Acceptance Criteria

| Metric | Before | After | Threshold |
|--------|--------|-------|-----------|
| semantic_entity intents per repo | ~58 | 1 | Must be 1 |
| Total reducer queue size (896 repos) | ~57K | ~6.2K | < 10K |
| Full queue drain time | ~4+ hours | < 45 minutes | < 1 hour |
| Terminal failures | 0 | 0 | Must be 0 |
| Error rate (retryable) | 0.006% | <= 0.006% | < 1% |

## Key Source Files

| File | Relevance |
|------|-----------|
| `go/internal/projector/semantic_entity_intents.go:23-68` | Per-entity intent builder (change target) |
| `go/internal/projector/runtime.go:222-224` | Intent generation loop in buildProjection() |
| `go/internal/reducer/semantic_entity_materialization.go:45-106` | Handler — verify works with per-repo intents |
| `go/internal/storage/neo4j/semantic_entity.go:269-376` | WriteSemanticEntities — already batches per UNWIND |
| `go/internal/storage/neo4j/semantic_entity.go:14-237` | All 11 label Cypher templates |
| `go/internal/storage/postgres/reducer_queue.go:30-73` | Claim query — domain filter unused |
| `go/internal/storage/postgres/reducer_queue.go:149-182` | Enqueue — batched multi-row INSERT at 500 |
| `go/internal/storage/postgres/reducer_queue_batch.go:11-54` | Batch claim query |
| `go/internal/storage/postgres/reducer_queue_batch.go:98-142` | AckBatch — single UPDATE with IN clause |
| `go/internal/reducer/shared_projection_runner.go` | SharedProjection — wrong abstraction for this |
| `go/cmd/reducer/config.go:24-52` | Worker count and batch claim size config |
| `docker-compose.yaml:349` | `PCG_REDUCER_WORKERS=4` default |

## Appendix: Queue Overhead Math

### Current (per-entity, 51,806 intents)

```
Postgres round-trips:
  Claim:    51,806 / 16 (batch size) = 3,238 claim queries
  Ack:      51,806 / 16             = 3,238 ack queries
  ListFacts: 51,806                  = 51,806 fact load queries
  Total:    ~58,282 Postgres round-trips

Neo4j round-trips:
  Write:    51,806 sessions × 1 GroupExecutor call = 51,806

Wall clock (4 workers, 1.2s avg per item):
  51,806 / 4 = 12,952 items per worker
  12,952 × 1.2s = 15,542s = ~4.3 hours
```

### After Option A (per-repo, 889 intents)

```
Postgres round-trips:
  Claim:    889 / 16  = 56 claim queries
  Ack:      889 / 16  = 56 ack queries
  ListFacts: 889       = 889 fact load queries
  Total:    ~1,001 Postgres round-trips (58x reduction)

Neo4j round-trips:
  Write:    889 sessions × 1 GroupExecutor call = 889
  (each session processes ~58 entities with UNWIND batching)

Wall clock (4 workers, ~5s avg per repo at 58 entities):
  889 / 4 = 222 items per worker
  222 × 5s = 1,110s = ~18.5 minutes
```

### Savings

| Resource | Before | After | Reduction |
|----------|--------|-------|-----------|
| Postgres round-trips | 58,282 | 1,001 | **58x** |
| Neo4j sessions | 51,806 | 889 | **58x** |
| Queue rows in fact_work_items | 57,140 | 6,223 | **9.2x** |
| Estimated drain time | 4.3 hours | 18.5 minutes | **14x** |
| Postgres CPU (queue overhead) | ~84% | ~15% (est) | **5.6x** |
