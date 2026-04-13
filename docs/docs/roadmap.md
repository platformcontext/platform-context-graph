# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current Phase

PCG is in **Phase 3: resolution maturity**.

Phase 3 keeps the facts-first runtime stable while we harden the operator
experience:

- durable facts land in Postgres
- the work queue drives projection, replay, and recovery
- `resolution-engine` owns canonical graph projection
- the deployed runtime shape remains `api` + `ingester` + `resolution-engine`
- telemetry, logs, traces, and admin/status views match that shape

The immediate goal is simpler operations, not new product surface:

- classify failures durably
- expose replay, dead-letter, audit, and backfill controls
- persist projection decisions with evidence and confidence summaries
- make admin and CLI inspection surfaces consistent

## Next Phase

### Phase 4: Go Data-Plane Rewrite

Replace the current Python write path with a schema-first Go data plane.

The rewrite introduces:

- scope-first ingestion contracts
- first-class ingestion scopes and scope generations
- typed facts and queueable change units
- source-local projection separated from shared reduction
- read-only API, MCP, and CLI surfaces over canonical state

Why it comes next:

- the current write path is the main scale bottleneck
- AWS, Kubernetes, and data/ETL collectors need a non-repository substrate
- the new design is the right place to lock in accuracy, stability, telemetry,
  tracing, and logging before collector count grows

The rewrite contract for this phase is captured in:

- [Architecture](architecture.md)
- [Architecture Decision Records](adrs/index.md)

The rewrite proof and documentation package is complete, but the Git
write-plane conversion is still in progress. No new ingestors start until the
Git cutover finishes.

## Rewrite Milestones

| Milestone | Outcome | Effort | Validation focus |
| --- | --- | --- | --- |
| 0 | Lock contracts, docs, and operator/admin rules | Small | docs build, contract freeze, no ambiguity in workstream ownership |
| 1 | Native Git cutover and operability | Large | collector/projector/reducer runtime proof, shared admin/status surfacing, end-to-end bounded Git path |
| 2 | Scope-first ingestion and incremental refresh | Large | scope/generation lifecycle, replay-safe refresh, no full re-index dependency |
| 3 | Canonical truth layers and reducer ownership | Large | cross-source correlation, layered truth, canonical-first query behavior |
| 4 | Legacy write-path retirement | Medium | proof bridge removal, regression coverage, no new logic on the old seam |
| 5 | Documentation and operator guidance | Medium | locked runbooks, traversal maps, collector onboarding, and truthful operator surfaces |

## Rewrite Status Notes

Milestone 1 on the rewrite branch is now defined by a truthful bounded outcome:

- Go owns collector orchestration, fact commit, projector/reducer runtime proof,
  and the shared admin/metrics story
- repository selection and per-repo parser snapshotting remain narrow
  transitional Python adapters
- full parser-bridge retirement is deferred to later rewrite milestones instead
  of being implied by Milestone 1

The branch is not done yet. The hard merge bar is still the Git write-plane
cutover:

- no deployed write service starts from Python runtime entrypoints
- no Go write-plane service imports `go/internal/compatibility/pythonbridge`
- no Python bridge modules under `src/platform_context_graph/runtime/ingester/`
  are required for normal Git ingestion
- no normal recovery or refinalize path depends on Python finalization bridge
  code
- Docker Compose and Helm run the Go-owned write plane
- local and cloud validation prove parity for the Git write path

No new ingestors before Git cutover completes.

## After That

### Phase 5: Multi-Collector Expansion

After the Go data plane is in place, add new collectors without changing the
core platform contract.

- start with the next source family, likely AWS
- add Kubernetes and other infrastructure collectors on the same scope model
- keep Git, cloud, and data sources aligned through shared reducers
- validate code -> IaC -> cloud -> workload -> data graph flows end to end

That phase should start from the locked rewrite docs, not from fresh design
debates. Future collector work should reuse the scope/generation/fact/reducer
model and the shared operator/admin contract documented in this branch.

### Phase 6: Backend And Scale Validation

Use the rewritten data plane and the first multi-collector workloads to measure
what actually limits scale.

- measure canonical graph write contention
- measure fact-store and queue pressure
- measure reducer throughput and saturation
- decide whether the backend mix still fits the workload
- evaluate alternatives only with real performance evidence

### Phase 7: Collector Framework Maturity

After the first multi-collector proof is stable, harden the collector
framework itself.

- standardize collector onboarding and telemetry
- keep collector families additive instead of special-case
- remove transitional bridge paths once parity is proven
- make new source families follow the same scope/generation/fact/reducer shape

## Longer-term

- Deeper cloud scanning and freshness pipelines
- Stronger semantic resolution and ranking
- Richer environment comparison and blast-radius analysis
- Broader language and IaC coverage
