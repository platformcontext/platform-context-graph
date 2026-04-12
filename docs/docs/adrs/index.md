# Architecture Decision Records

This section captures the accepted design decisions that lock down the next
rewrite phase for PlatformContextGraph.

Use these ADRs when you need the durable answer to "why is the platform shaped
this way?" They are the decision companion to the higher-level public
[Architecture](../architecture.md) and [Roadmap](../roadmap.md) pages.

The current accepted ADR set establishes the rewrite baseline:

- [Go Data Plane in a Monorepo](2026-04-12-go-data-plane-monorepo.md)
  defines the repository boundary, multi-service runtime stance, and the move
  to Go plus Buf/Protobuf contracts on the write side.
- [Scope-First Ingestion](2026-04-12-scope-first-ingestion.md) defines
  `ingestion_scopes` and `scope_generations` as the durable ingestion contract
  for Git, cloud, Kubernetes, and future collectors.
- [Reducer Intent Architecture](2026-04-12-reducer-intent-architecture.md)
  defines the split between source-local projection and asynchronous shared
  reduction, along with canonical-first query and MCP behavior.

Read these records together. They are meant to remove ambiguity before new
collector or runtime work begins.
