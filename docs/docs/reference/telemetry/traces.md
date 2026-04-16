# Telemetry Traces

Traces answer one question better than any other signal:

**Where did the time go for this specific request, scope, queue item, or
graph write?**

Use metrics to detect a problem first, then use traces to explain which stage,
store, or runtime spent the time.

## Current Go Trace Contract

The current branch is Go-owned. The trace contract is therefore the Go data
plane contract from `go/internal/telemetry/contract.go` plus the read-path
query wrappers.

The stable span families are:

- `collector.observe`
- `collector.stream`
- `scope.assign`
- `fact.emit`
- `projector.run`
- `reducer_intent.enqueue`
- `reducer.run`
- `reducer.batch_claim`
- `canonical.write`
- `canonical.projection`
- `canonical.retract`
- `ingestion.evidence_discovery`
- `reducer.sql_relationship_materialization`
- `reducer.inheritance_materialization`
- `reducer.cross_repo_resolution`
- `postgres.exec`
- `postgres.query`
- `neo4j.execute`

The read/query layer also emits:

- `postgres.query`
- `neo4j.query`
- `neo4j.query.single`

The older Python-era families such as `pcg.http.*`, `pcg.mcp.*`, `pcg.query.*`,
`pcg.index.*`, `pcg.fact_*`, `pcg.resolution.*`, `pcg.graph.*`, and
`pcg.content.*` are not the current Go trace contract on this branch.

## How To Read The Trace Tree

### Collector and snapshot path

- `collector.observe` is the top-level collect-and-commit cycle
- `collector.stream` covers the per-scope streaming collection path
- `scope.assign` explains repository selection and scope assignment
- `fact.emit` covers parsing, snapshot shaping, and fact emission for one scope
- child `postgres.exec` and `postgres.query` spans explain Postgres cost inside
  the collector path

### Projector path

- `projector.run` is one projector claim-and-project cycle
- `canonical.projection` is the scoped materialization sub-phase
- `canonical.write` is the graph/content write phase
- `reducer_intent.enqueue` covers follow-up reducer intent creation
- child `neo4j.execute`, `postgres.exec`, and `postgres.query` spans show store
  cost within the projection cycle

### Reducer path

- `reducer.run` is one reducer claim-and-execute cycle
- `reducer.batch_claim` covers batched reducer claim work where used
- `reducer.cross_repo_resolution` is the cross-repo relationship resolution span
- `reducer.sql_relationship_materialization` covers SQL-side relationship
  materialization
- `reducer.inheritance_materialization` covers inheritance/write follow-up
  materialization
- `canonical.write` covers shared projection or canonical edge writes

### Read path

- `postgres.query` traces content-store reads
- `neo4j.query` and `neo4j.query.single` trace graph-backed reads

The read path is intentionally narrower than the write path. It traces storage
cost, not a synthetic Python-era HTTP or MCP span family.

## Key Attributes

The most useful span attributes on the Go path are:

- `scope_id`
- `scope_kind`
- `source_system`
- `generation_id`
- `collector_kind`
- `domain`
- `partition_key`
- `db.system`
- `db.operation`

For query traces, also pay attention to:

- repo identifiers or entity identifiers added by the caller
- runtime/store labels such as `pcg.store`

## Investigation Recipes

### A scope is slow to collect

1. Start with `pcg_dp_collector_observe_duration_seconds`.
2. Open the `collector.observe` trace.
3. Check whether time is concentrated in `scope.assign`, `fact.emit`, or child
   Postgres calls.

### Projector backlog is not draining

1. Start with `pcg_dp_queue_depth{queue=projector}` and
   `pcg_dp_queue_oldest_age_seconds{queue=projector}`.
2. Open `projector.run` traces for the slow period.
3. Compare fact-load `postgres.query` spans with `canonical.write` and nested
   `neo4j.execute` spans.

### Reducer relationship work is slow

1. Start with `pcg_dp_reducer_run_duration_seconds` and reducer queue depth.
2. Open `reducer.run` traces.
3. Look for time in `reducer.cross_repo_resolution`,
   `reducer.sql_relationship_materialization`,
   `reducer.inheritance_materialization`, or nested `canonical.write`.

### Graph writes are slow

1. Start with `pcg_dp_canonical_write_duration_seconds`.
2. Open `canonical.write`.
3. Check nested `neo4j.execute` spans and any surrounding reducer/projector
   phase span to see which caller owns the slow write.

### Read path is slow

1. Start with the API or MCP latency metrics for the affected runtime.
2. Open the corresponding query trace.
3. Use `postgres.query`, `neo4j.query`, and `neo4j.query.single` to determine
   whether the tail is in Postgres, Neo4j, or the caller’s shaping code.

## What This Page Does Not Claim

- It does not claim a Python-style universal `pcg.query.*` family.
- It does not claim every log line has a matching explicit `event_name`.
- It does not claim replay, admin, or recovery flows have their own special
  legacy trace namespace. They run through the same Go runtime and store spans
  listed above.
