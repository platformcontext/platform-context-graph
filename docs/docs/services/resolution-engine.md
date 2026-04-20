# Resolution Engine (Reducer)

## Role and Purpose

The Resolution Engine is a **long-running Deployment** that processes
cross-domain reducer intents and shared projection work. It takes the
source-local facts produced by the Ingester/Bootstrap-Index and materializes
canonical cross-repo relationships in the Neo4j graph.

**Binary**: `/usr/local/bin/pcg-reducer`
**Docker service name**: `resolution-engine`
**Kubernetes shape**: Deployment
**Source**: `go/cmd/reducer/`, `go/internal/reducer/`

## Workflow

```text
1. Initialize telemetry
2. Open Postgres (InstrumentedDB) and Neo4j (InstrumentedExecutor) connections
3. Build reducer service with:
   - DefaultRuntime executor (domain-specific handlers)
   - SharedProjectionRunner (canonical edge writer)
   - ReducerQueue (Postgres-backed work queue)
4. reducer.Service.Run() — two concurrent loops:

   Main reducer loop                SharedProjectionRunner
   ─────────────────                ──────────────────────
   loop forever:                    loop forever:
     claim 1 intent from queue        for each domain (4 types):
     execute domain handler             for each partition (8 default):
     on success: ack intent               acquire partition lease
     on failure: fail intent              read pending intents (batch 100)
     if no work: sleep 1s                 filter by accepted generation
                                          write edges to Neo4j
                                          ack processed intents
                                        if no work: sleep 5s
```

## Intent Domains

The reducer processes 8 intent domains:

| Domain | Handler | Purpose |
|--------|---------|---------|
| `workload_identity` | PostgresWorkloadIdentityWriter | Resolve canonical workload identity |
| `cloud_asset_resolution` | PostgresCloudAssetResolutionWriter | Resolve cloud asset identity |
| `deployment_mapping` | (registered handler) | Resolve deployment relationships |
| `data_lineage` | (registered handler) | Resolve cross-source lineage |
| `ownership` | (registered handler) | Resolve ownership records |
| `governance` | (registered handler) | Resolve governance attribution |
| `workload_materialization` | WorkloadMaterializer (Cypher) | Materialize workload graph nodes |
| `code_call_materialization` | CodeCallEdgeWriter (Neo4j) | Materialize code call edges |

## Shared Projection

The SharedProjectionRunner handles 4 canonical edge types that span repos:

| Edge Type | Cypher Operation |
|-----------|-----------------|
| `platform_infra` | MERGE infrastructure-platform relationships |
| `repo_dependency` | MERGE repository dependency edges |
| `workload_dependency` | MERGE workload dependency edges |
| `code_calls` | MERGE code call edges |

Processing model:

- **Partitions**: 8 by default (`PCG_SHARED_PROJECTION_PARTITION_COUNT`)
- **Lease-based**: Each partition acquired via time-limited lease (60s TTL)
- **Batch reads**: Up to 100 intents per partition per cycle
- **Generation filtering**: Only processes intents for accepted generations

## Concurrency Model

- **Main reducer loop**: Sequential by default (Workers=0). Supports concurrent
  workers but this is not enabled in production wiring.
- **SharedProjectionRunner**: Sequential by default (Workers=1). Supports
  concurrent partition workers via `PCG_SHARED_PROJECTION_WORKERS`.
- **Both loops run as concurrent goroutines** within `Service.Run()`.

## Backing Stores

| Store | Usage |
|-------|-------|
| Postgres | Intent queue (claim/ack/fail), shared intent store, fact lookups, workload/cloud asset writes |
| Neo4j | Canonical edge writes (per-row), workload/infrastructure materialization (Cypher) |

## Configuration

| Env Var | Default | Purpose |
|---------|---------|---------|
| `PCG_REDUCER_RETRY_DELAY` | 30s | Retry delay for failed intents |
| `PCG_REDUCER_MAX_ATTEMPTS` | 3 | Max retry attempts |
| `PCG_SHARED_PROJECTION_WORKERS` | 1 | Concurrent shared projection workers |
| `PCG_SHARED_PROJECTION_PARTITION_COUNT` | 8 | Number of partitions |
| `PCG_SHARED_PROJECTION_POLL_INTERVAL` | 5s | Poll interval when idle |
| `PCG_SHARED_PROJECTION_LEASE_TTL` | 60s | Partition lease duration |
| `PCG_SHARED_PROJECTION_BATCH_LIMIT` | 100 | Max intents per partition read |

## Telemetry

| Signal | Instruments |
|--------|-------------|
| Spans | `reducer.run` (per intent), `canonical.write` (per partition cycle) |
| Histograms | `pcg_dp_reducer_run_duration_seconds`, `pcg_dp_canonical_write_duration_seconds`, `pcg_dp_queue_claim_duration_seconds{queue=reducer}` |
| Counters | `pcg_dp_reducer_executions_total` (domain + status attrs), `pcg_dp_shared_projection_cycles_total` |
| Logs | `reducer execution succeeded/failed` (domain, intent_id, worker_id), `shared projection cycle completed` |

---

## Optimization Opportunities

### Performance

**1. Canonical edge writes are per-row** (`storage/neo4j/edge_writer.go:36-42`)

This is the single biggest performance bottleneck in the reducer.
`EdgeWriter.WriteEdges()` executes one Cypher statement per row for all 4
shared projection domains. At scale (thousands of cross-repo edges per cycle),
this means thousands of Neo4j round-trips.

- **Fix**: Batch UNWIND for edge writes. Group rows by domain, convert to
  parameter maps, execute as `UNWIND $rows AS row MERGE ...` in batches of
  500 (matching the source-local writer pattern).
- **Impact**: Largest win. Reduces round-trips by ~500x for edge-heavy domains.

**2. Single-item claim per poll** (`reducer/service.go:110`)

`Claim()` returns at most 1 intent per poll. Each claim is a Postgres
round-trip with row lock. Fix: batch claim with `LIMIT 10`, process locally.
Reduces claim round-trips ~10x under load.

**3. SharedProjectionRunner is single-threaded by default**

Workers=1 processes 4 domains x 8 partitions = 32 cycles sequentially.
Fix: raise `PCG_SHARED_PROJECTION_WORKERS` default to `min(NumCPU, 4)`.
The concurrent path already exists in `runOneCycleConcurrent()`.

**4. No concurrent reducer workers enabled**

`Service.Workers` defaults to 0 (sequential). The concurrent path exists
but isn't activated. Fix: wire `PCG_REDUCER_WORKERS` env var, default to
`min(NumCPU, 4)`. Queue uses `FOR UPDATE SKIP LOCKED` so this is safe.

**5. InstrumentedExecutor batch metrics gap**

Once edge write batching is added (#1), ensure `InstrumentedExecutor`
records batch size and duration correctly on the reducer's Neo4j path.

### SRE / Operability

**6. No queue depth visibility for reducer intents**

Operators can't see pending intent backlog from dashboards. Fix: periodic
gauge for `SELECT count(*) FROM reducer_queue WHERE claimed_at IS NULL`,
broken down by domain.

**7. No per-intent-domain metrics at partition level**

Shared projection metrics don't differentiate between edge domains per
partition. Fix: add `domain` and `partition_id` attributes to
`SharedProjectionCycles` and `CanonicalWriteDuration`.

**8. Stale claim detection is passive**

Recovery runner reclaims stale items but no metric alerts operators. Fix:
counter `pcg_dp_reducer_stale_reclaims_total` and gauge for oldest stale
item age.

**9. No shared projection lag metric**

Fix: gauge for oldest unprocessed shared projection intent timestamp.
Answers "how stale is the canonical graph?" and enables SLA alerting.

### Accuracy / Correctness

**10. Partial projection on error leaves inconsistent graph**

If `EdgeWriter.WriteEdges()` fails mid-batch, some edges are written and
others are not. Fix: wrap shared projection writes in a Neo4j explicit
transaction so all edges for a partition cycle commit or roll back atomically.
Alternative: ensure projection is fully idempotent so re-runs converge.

**11. No generation-aware edge cleanup**

Old-generation edges may persist after re-ingestion. The retract path exists
in `EdgeWriter.RetractEdges()` but relies on the intent system to trigger
retraction. Fix: delete-before-write pattern, or generation-stamped edges
with periodic GC.

**12. Intent deduplication gap**

Projector retries may re-enqueue the same reducer intent. Fix: upsert
semantics on intent enqueue
(`ON CONFLICT (scope_id, generation_id, domain) DO NOTHING`).

---

## Priority Matrix

| # | Category | Impact | Effort | Priority |
|---|----------|--------|--------|----------|
| 1 | Performance | Very High | Medium | P0 |
| 4 | Performance | High | Low | P0 |
| 3 | Performance | High | Low | P0 |
| 2 | Performance | Medium | Medium | P1 |
| 6 | SRE | High | Low | P1 |
| 12 | Accuracy | Medium | Low | P1 |
| 7 | SRE | Medium | Low | P2 |
| 8 | SRE | Medium | Low | P2 |
| 10 | Accuracy | Medium | Medium | P2 |
| 5 | Performance | Low | Low | P3 |
| 9 | SRE | Low | Low | P3 |
| 11 | Accuracy | Low | Medium | P3 |
