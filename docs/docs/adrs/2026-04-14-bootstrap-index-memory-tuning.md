# ADR: Bootstrap-Index Memory Tuning

**Status:** Active (tuning in progress)

## Context

Bootstrap-index OOMed repeatedly when indexing 878 repositories on a 123 GiB
production machine (ubuntu@10.208.198.57). The investigation identified three
compounding root causes, each requiring a separate fix. This ADR documents the
causes, the fixes applied, and the runtime tuning knobs so future operators
can reproduce the reasoning.

## Root Cause Analysis

### Cause 1: Unbounded In-Memory Buffering (fixed in prior session)

The original `GitSource.buildCollected()` snapshotted ALL repositories into a
`[]CollectedGeneration` slice before returning any to the consumer. With 878
repos at ~130 MB average, this peaked at ~115 GiB.

**Fix:** Replaced the slice accumulator with a streaming channel architecture.
Background snapshot workers feed results through a bounded channel. The consumer
(`drainCollector`) reads one generation at a time, commits it to Postgres, then
reads the next. Workers block on send when the channel is full, providing
natural backpressure.

### Cause 2: N+1 Fact INSERT Pattern (fixed in prior session)

Each `CollectedGeneration` contained up to 91,961 fact envelopes. The original
`upsertFacts` issued one `INSERT` per fact — 91k round trips per large repo.
This made the Postgres consumer so slow that streaming workers piled up
generations faster than they could be committed, defeating the backpressure
mechanism.

**Fix:** Batched multi-row INSERT with 500 rows per query (6,500 parameters,
well under the Postgres 65,535 limit). Reduced 91k round trips to ~184 queries.
Added `deduplicateEnvelopes()` to handle duplicate `fact_id` values within a
batch, which Postgres rejects with SQLSTATE 21000 on `ON CONFLICT DO UPDATE`.

### Cause 3: Channel Buffer Sized to Worker Count

```go
s.stream = make(chan CollectedGeneration, workers)  // buffer of 8
```

With `SnapshotWorkers=8`, the channel buffer held 8 completed generations plus
8 more being built by workers, plus 1 being consumed — 17 repo generations
simultaneously in memory. When several large repos were processed concurrently,
peak RSS reached 60+ GiB at only 400/878 scopes and was climbing toward OOM.

**Fix:** Changed the channel buffer to 1 regardless of worker count. This
bounds live memory to `(1 buffer + workers in-flight + 1 consuming)` generations.
With `SnapshotWorkers=2`, that's 4 max generations instead of 17.

### Cause 4: GOMEMLIMIT Too Aggressive

`GOMEMLIMIT=8GiB` instructs the Go GC to target 8 GiB heap. When the genuine
live working set exceeds 8 GiB (because multiple large repo generations are
simultaneously referenced), the GC enters a continuous panic loop: it runs
constantly trying to reduce heap below 8 GiB, fails because the objects are
still live, and wastes CPU on futile collection cycles. The 1100% CPU observed
was largely GC overhead. This slows the consumer, which increases backpressure,
which keeps more generations in memory — a negative feedback loop.

**Fix:** Increased `GOMEMLIMIT` to 64 GiB. This lets the GC run at normal
cadence instead of thrashing. Combined with the buffer-of-1 fix, the working
set should stay well under 64 GiB.

### Cause 5: MADV_FREE vs MADV_DONTNEED (addressed in prior session)

Go's default memory advice (`MADV_FREE`) marks freed pages as reusable but does
not release them to the OS. Docker stats reports RSS including these pages,
making it appear that memory never drops even when GC runs successfully.

**Fix:** `GODEBUG=madvdontneed=1` forces Go to use `MADV_DONTNEED`, which
immediately releases RSS pages to the OS. This makes docker stats reflect actual
live memory and prevents the kernel OOM killer from targeting the container
based on inflated RSS.

## Runtime Tuning Knobs

| Variable | Default | Current Production | Purpose |
|---|---|---|---|
| `PCG_SNAPSHOT_WORKERS` | 8 | **2** | Concurrent repo snapshot goroutines. Lower = less concurrent memory, slower throughput. |
| `PCG_GOMEMLIMIT` | 8GiB | **64GiB** | Go GC heap target. Must exceed the expected live working set or GC thrashes. |
| `GODEBUG` | (none) | `madvdontneed=1` | Forces immediate RSS release on GC. Required for accurate docker stats and to avoid kernel OOM on inflated RSS. |

### Tuning Guidelines

1. **Start with `PCG_SNAPSHOT_WORKERS=2`** on machines with < 64 GiB RAM.
   Increase to 4 or 8 only after confirming peak RSS stays under 50% of
   available memory.

2. **Set `PCG_GOMEMLIMIT` to ~50% of available container memory.** On a 123 GiB
   machine, 64 GiB is appropriate. On a 32 GiB machine, use 16 GiB. Setting it
   too low causes GC thrashing; too high risks the kernel OOM killer.

3. **Always set `GODEBUG=madvdontneed=1`** in containerized deployments.
   Without it, RSS appears inflated and the kernel may OOM-kill the process
   even when live heap is well within limits.

4. **Peak memory formula:**
   ```
   peak ≈ (1 + workers + 1) × avg_large_repo_generation_size
   ```
   With workers=2 and avg large repo ~4 GiB: peak ≈ 16 GiB.
   With workers=8 and avg large repo ~4 GiB: peak ≈ 40 GiB.

## Observation Log

| Attempt | Workers | Buffer | GOMEMLIMIT | GODEBUG | Peak RSS | Scopes at Peak | Outcome |
|---|---|---|---|---|---|---|---|
| 1 | 8 | unbounded (slice) | none | none | 115 GiB | 878 | OOM exit 137 |
| 2 | 8 | 8 (channel) | none | none | 73 GiB | ~350 | OOM exit 137 |
| 3 | 8 | 8 | 8GiB | none | 37 GiB | 315 | continued |
| 4 | 8 | 8 | 8GiB | madvdontneed=1 | 100 GiB | 413 | killed (trending OOM) |
| 5 | 2 | 1 | 64GiB | madvdontneed=1 | 42 GiB | 146 | exit 1: SQLSTATE 22P05 |
| 6 | 2 | 1 | 64GiB | madvdontneed=1 | TBD | TBD | **in progress** |

### Cause 6: Null Unicode Escapes in JSONB (SQLSTATE 22P05)

Attempt 5 showed memory behavior was correct (20 GiB at 136 scopes, GC
reclaiming normally, CPU at 125% vs 1100% before). However, a repo with
295,347 facts contained `\u0000` (null byte) Unicode escape sequences in
source code content payloads. Postgres JSONB rejects these with SQLSTATE
22P05 ("unsupported Unicode escape sequence").

**Fix:** Added `sanitizeJSONBNullEscapes()` in `marshalPayload()` to strip
`\u0000` sequences before insertion. This is a safe transformation since null
bytes in JSON strings have no meaningful representation in Postgres JSONB.

## Decision

The streaming architecture with batched INSERT is the correct long-term design.
The remaining tuning is operational: worker count and GOMEMLIMIT should be
sized to the deployment machine's available RAM using the formula above.

Future improvements:
- Per-repo memory profiling to identify outlier repos consuming disproportionate memory
- Adaptive worker count that scales down when individual repo generations are large
- Streaming facts within a single large repo (sub-repo granularity) if repos exceed available memory individually
