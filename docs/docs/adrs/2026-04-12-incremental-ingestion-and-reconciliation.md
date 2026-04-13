# ADR: Incremental Ingestion And Reconciliation

**Status:** Accepted

## Context

PCG will eventually ingest large repository sets, cloud inventories, clusters,
and data platforms. A full re-index after every update would waste compute,
increase latency, and make the platform feel brittle under normal change
volume.

The architecture already has durable scope and generation boundaries, which
means the platform can reconcile change incrementally instead of redoing the
entire world every time a source changes.

## Decision

PCG will use **incremental ingestion and reconciliation** by default.

Rules:

- collectors refresh only the affected scope or scope shard
- new generations describe the changed unit of truth for that scope
- reducers reconcile the canonical graph from the changed scope generation
- full re-index is not the normal path for routine updates
- full rebuilds remain available as explicit bootstrap or recovery actions

If a source cannot provide a precise delta, the collector should rescan the
smallest practical bounded scope instead of expanding to a platform-wide
reindex.

## Why This Choice

- It keeps refresh latency aligned with actual change size.
- It avoids turning large estates into repeated cold starts.
- It fits cloud, Kubernetes, SQL, and repo-backed sources that change at
  different cadences.
- It preserves replay and backfill correctness through durable generations.

## Consequences

Positive:

- Better throughput and lower operational cost.
- Faster operator feedback when only a small source slice changed.
- Easier selective replay and backfill.

Tradeoffs:

- Incremental state tracking becomes mandatory.
- Collectors and reducers must be careful about deletes, drift, and stale
  records.
- Coverage gaps must be visible instead of silently hidden by a full rebuild.

## Implementation Guidance

- Treat scope-generation boundaries as the unit of incremental refresh.
- Prefer targeted reconciliation over a global rebuild.
- Keep bootstrap and recovery paths explicit so they do not become the default.
- Record coverage gaps and unsupported deltas so operators know when a source
  needed a bounded rescan.
