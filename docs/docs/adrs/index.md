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
- [Layered Truth And Asset Identity](2026-04-12-layered-truth-and-asset-identity.md)
  defines the truth layers and the provider-native-first identity rules that
  connect declared, applied, observed, and canonical infrastructure state.
- [Logical Workload Spine](2026-04-12-logical-workload-spine.md) defines the
  logical workload model, runtime instances, and how ETL and job systems fit
  into the same workload spine without collapsing data assets into workloads.
- [Observability Contract](2026-04-12-observability-contract.md) defines the
  required telemetry, tracing, and structured logging contract for the new data
  plane.
- [Resiliency And Concurrency Contract](2026-04-12-resiliency-and-concurrency-contract.md)
  defines where PCG should use bounded channels and worker pools, where it must
  keep durable queue boundaries, and how resiliency and backpressure are
  treated as first-class platform rules.
- [Cutover And Legacy Bridge](2026-04-12-cutover-and-legacy-bridge.md) defines
  the transition model away from the current Python-heavy procedural write path
  without keeping two long-lived architectures alive.

Read these records together. They are meant to remove ambiguity before new
collector or runtime work begins.
