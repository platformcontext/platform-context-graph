# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current Phase

PCG is in **Phase 4: Go platform completion and validation**.

The normal runtime and parser path on this branch are now Go-owned. The active
work is making that cutover truthful, verifiable, and mergeable:

- finish remaining parity validation for parser and relationship surfaces
- remove stale Python-oriented packaging, docs, and compatibility references
- keep Docker Compose, Helm, admin/status, telemetry, and OpenAPI aligned with
  the Go-owned runtime
- prove the branch is ready for merge before starting any new ingestor family

The rewrite contract for the current cutover is captured in:

- [Architecture](architecture.md)
- [Architecture Decision Records](adrs/index.md)

No new ingestors start until the full conversion is validated and the last
stale Python-oriented ownership claims are removed from the repo.

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

Current remaining work is no longer active Python service ownership on the
normal path. It is:

- parity hardening for the Go parser and relationship surfaces
- validation proof across compose, runtime, telemetry, and admin/status flows
- deletion of stale Python-specific packaging and contributor scaffolding that
  no longer reflects the branch reality

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
