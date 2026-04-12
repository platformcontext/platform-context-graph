# ADR: Reducer Intent Architecture

**Status:** Accepted

## Context

PCG needs to correlate source-local truth into canonical cross-source truth
without turning the write path into a long procedural chain. The platform will
soon ingest Git, cloud, Kubernetes, ETL, and infrastructure state. Each source
has a natural local projection step, but shared concepts such as workload
identity, cloud asset resolution, deployment mapping, data lineage, governance,
and ownership require asynchronous cross-source reconciliation.

The existing pattern of doing too much follow-up work inline after each ingest
run does not scale well as more collectors and domains are added.

## Decision

PCG will use a **reducer-intent architecture**.

The flow is:

1. A collector observes a bounded scope.
2. The source-local projector materializes local truth for that
   `scope_generation`.
3. The projector emits durable reducer intents for shared domains.
4. Reducer workers drain those intents asynchronously.
5. Reducers update canonical graph state.
6. Query and MCP surfaces read the canonical result by default.

Reducer intents are durable records. They are keyed by the authoritative
scope-generation boundary, not by ad hoc mutation events or a collector's
temporary execution state.

## Flow

```mermaid
flowchart LR
  A["Collector"] --> B["Scope generation"]
  B --> C["Source-local projector"]
  C --> D["Durable reducer intent queue"]
  D --> E["Domain reducers"]
  E --> F["Canonical graph"]
  F --> G["Query and MCP"]
```

## Why Durable Scope-Generation Intents

- A scope generation is the authoritative change boundary.
- Deletes, retractions, and freshness are only correct when the source snapshot
  itself is the unit of truth.
- Durable intents make replay and recovery deterministic.
- The reducer scheduler can derive and coalesce entity-level work from the
  scope-generation boundary without losing correctness.
- This keeps the platform accurate even when many collectors and sources are
  running at once.

## Why Async Reducers

- Shared correlation work should not extend collector latency.
- Different reducer domains will have different throughput and contention
  characteristics.
- Async reducers keep source-local projection fast while still allowing the
  system to converge on canonical truth.
- This is the best way to prevent PCG from becoming a procedural beast.

## Canonical-First Query And MCP

The public query contract must default to canonical resolved truth.

That means:

- the primary answer should be the best resolved view of the graph
- source-local or raw evidence is opt-in
- explicit modes such as `evidence`, `raw`, `explain`, or `freshness` can reveal
  the underlying source details when needed
- users and downstream agents should not have to know the internal reducer
  topology to ask ordinary questions

This default keeps the platform usable as a knowledge base while preserving the
ability to inspect the evidence behind a result.

## Consequences

Positive:

- Source-local work stays bounded and fast.
- Cross-source correlation gets a durable execution model.
- The system can scale by domain instead of by one giant finalization step.
- Canonical answers stay clean and usable.
- Replay and backfill remain deterministic.

Tradeoffs:

- The reducer scheduler becomes a first-class part of the platform.
- Some answers will be eventually consistent until the relevant reducer domain
  drains.
- Observability must clearly show which layer produced a result and which layer
  still has pending work.

## Implementation Guidance

- Make reducer intents durable and scope-generation keyed.
- Let the scheduler derive entity-keyed batches as an optimization, not as the
  durable queue record.
- Keep domain ownership explicit. Examples include workload identity, cloud
  asset resolution, deployment mapping, data lineage, governance, and ownership.
- Keep source-local projection inline to the collector's generation, but keep
  shared reconciliation out of the collector hot path.
- Retire procedural finalization paths instead of adding more stages to them.
