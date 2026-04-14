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
- [Source-Specific Ingestors And Shared Fact Contract](2026-04-12-source-specific-ingestors-and-shared-fact-contract.md)
  defines the service-per-source boundary and the stable fact handoff shared by
  every collector.
- [Scope-First Ingestion](2026-04-12-scope-first-ingestion.md) defines
  `ingestion_scopes` and `scope_generations` as the durable ingestion contract
  for Git, cloud, Kubernetes, and future collectors.
- [Incremental Ingestion And Reconciliation](2026-04-12-incremental-ingestion-and-reconciliation.md)
  defines selective refresh and reconciliation as the normal path instead of
  full re-indexes.
- [Resolution Owns Cross-Domain Truth](2026-04-12-resolution-owns-cross-domain-truth.md)
  defines the hard ownership split between collectors, source-local projectors,
  and reducer-owned canonical truth.
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
- [Service Admin And Observability Contract](2026-04-12-service-admin-and-observability-contract.md)
  defines the standard health, readiness, status, and metrics surface every
  long-running service must expose.
- [Resiliency And Concurrency Contract](2026-04-12-resiliency-and-concurrency-contract.md)
  defines where PCG should use bounded channels and worker pools, where it must
  keep durable queue boundaries, and how resiliency and backpressure are
  treated as first-class platform rules.
- [Cutover And Legacy Bridge](2026-04-12-cutover-and-legacy-bridge.md) defines
  the transition model away from the current Python-heavy procedural write path
  without keeping two long-lived architectures alive.
- [Go Data Plane Ownership Completion](2026-04-13-go-data-plane-ownership-completion.md)
  extends the write-plane conversion beyond deployment surfaces to cover full Go
  ownership of resolution domain logic, operational surfaces, and recovery
  endpoint migration.
- [Unified JSON Logging Standard](2026-04-13-unified-logging-standard.md)
  defines the canonical JSON log schema that every Go-owned runtime emits,
  enabling consistent cross-service log correlation in Grafana/Loki.

Read these records together. They are meant to remove ambiguity before new
collector or runtime work begins.
