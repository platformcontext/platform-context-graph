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

### Phase 4: Full Python-to-Go Platform Conversion

Replace the current Python-owned runtime and parser path with a schema-first Go
platform.

The conversion introduces:

- native Go parser ownership for the Git path
- scope-first ingestion contracts
- first-class ingestion scopes and scope generations
- typed facts and queueable change units
- source-local projection separated from shared reduction
- Go-owned runtime, admin, and repair surfaces over canonical state

Why it comes next:

- the current Python-owned runtime path is the main scale bottleneck
- AWS, Kubernetes, and data/ETL collectors need a non-repository substrate
- the new design is the right place to lock in accuracy, stability, telemetry,
  tracing, and logging before collector count grows

The rewrite contract for this phase is captured in:

- [Architecture](architecture.md)
- [Architecture Decision Records](adrs/index.md)

The rewrite proof and documentation package is complete, but the full
Python-to-Go platform conversion is still in progress. No new ingestors start
until the full conversion finishes.

## Rewrite Milestones

| Milestone | Outcome | Effort | Validation focus |
| --- | --- | --- | --- |
| 0 | Lock contracts, docs, and operator/admin rules | Small | docs build, contract freeze, no ambiguity in workstream ownership |
| 1 | Native parser platform and Git cutover | Large | parser parity, collector/projector/reducer runtime proof, shared admin/status surfacing, end-to-end bounded Git path |
| 2 | Scope-first ingestion and incremental refresh | Large | scope/generation lifecycle, replay-safe refresh, no full re-index dependency |
| 3 | Canonical truth layers and reducer ownership | Large | cross-source correlation, layered truth, canonical-first query behavior |
| 4 | Legacy runtime and bridge retirement | Medium | proof bridge removal, regression coverage, no new logic on the old seam |
| 5 | Documentation and operator guidance | Medium | locked runbooks, traversal maps, collector onboarding, and truthful operator surfaces |

## Rewrite Status Notes

Milestone 1 on the rewrite branch is now defined by a truthful bounded outcome:

- Go owns parser conversion, collector orchestration, fact commit,
  projector/reducer runtime proof, and the shared admin/metrics story
- repository selection, parser dispatch, and per-repo snapshotting are no
  longer treated as long-term Python ownership on the normal path
- full parser-bridge retirement is part of the conversion rather than a later
  optional cleanup

The branch is not done yet. The hard merge bar is still the full
Python-to-Go conversion:

- no deployed runtime or write service starts from Python runtime entrypoints
- no Go runtime service imports `go/internal/compatibility/pythonbridge`
- no Python bridge modules under `src/platform_context_graph/runtime/ingester/`
  are required for normal Git ingestion
- no normal parser, discovery, snapshot, content-shaping, recovery, refinalize,
  or admin-repair path depends on Python runtime ownership
- Docker Compose and Helm run the Go-owned platform
- local and cloud validation prove parity for the Git parser and write path

No new ingestors before full conversion completes.

## After That

### Phase 5: Multi-Collector Expansion

After the Go platform conversion is in place, add new collectors without
changing the core platform contract.

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
