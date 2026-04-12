# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current phase

PCG is in **Phase 3: resolution maturity**.

Phase 3 builds on the facts-first runtime established in Phase 2:

- Git indexing writes durable facts into Postgres
- a Postgres work queue coordinates projection work
- the `resolution-engine` owns canonical graph projection
- deployed runtime shape is `api` + `ingester` + `resolution-engine`
- telemetry, logs, traces, and operator runbooks align to the real service shape

The immediate goal in Phase 3 is to make the system easier to operate and trust:

- classify fact-projection failures durably instead of relying on logs alone
- add operator-grade replay, dead-letter, audit, and backfill controls
- persist projection decisions with evidence and confidence summaries
- expose richer admin and CLI inspection surfaces for work items and decisions
- strengthen documentation and test guidance before the next architectural step

## Next phase

### Phase 4: Go Data-Plane Rewrite

Replace the current Python write path with a schema-first Go data plane.

- introduce scope-first ingestion contracts
- add first-class ingestion scopes and scope generations
- move collector output into typed facts and queueable change units
- split source-local projection from shared cross-source reduction
- keep the API, MCP, and CLI read-only over canonical state
- keep the current facts-first behavior as the historical baseline while the
  new runtime lands

Why it comes next:

- the current write path is the main architectural bottleneck for future scale
- AWS, Kubernetes, and data/ETL collectors need a substrate that is not
  repository-shaped
- the new design is the best place to lock down accuracy, stability, telemetry,
  tracing, and logging before collector count grows

The rewrite contract for this phase is captured in:

- [Architecture](architecture.md)
- [Architecture Decision Records](adrs/index.md)

## After That

### Phase 5: Multi-Collector Expansion

After the Go data plane is in place, add new collectors without changing the
core platform contract.

- start with the next source family, likely AWS
- add Kubernetes and other infrastructure collectors on the same scope model
- keep Git, cloud, and data sources aligned through shared reducers
- validate code -> IaC -> cloud -> workload -> data graph flows end to end

Why it comes later:

- collectors should plug into a stable substrate, not define the substrate
- the rewrite should settle the platform contract before write volume expands
- a shared scope/generation model is the right base for enterprise-scale growth

### Phase 6: Backend And Scale Validation

Use the rewritten data plane and the first multi-collector workloads to measure
what actually limits scale.

- measure canonical graph write contention
- measure fact-store and queue pressure
- measure reducer throughput and saturation
- decide whether the backend mix still fits the workload
- evaluate alternatives only with real performance evidence

Why it still matters:

- the rewrite should give us reliable numbers instead of guesses
- backend decisions are better after the new write path and multiple collectors
  are operating on the same contract

## Longer-term

- Deeper cloud scanning and freshness pipelines
- Stronger semantic resolution and ranking
- Richer environment comparison and blast-radius analysis
- Broader language and IaC coverage
