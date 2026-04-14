# Roadmap

This roadmap is the single public place for forward-looking project direction.

## Current Phase

PCG has completed the **runtime migration** portion of Go platform completion.

The entire runtime, parser ownership boundary, CLI, and deployment surface are
Go-owned. There is no Python runtime code left in the repository — only Python
fixture files used as parser test data under `tests/fixtures/`. The Dockerfile
builds a single Go-only image and docker-compose runs exclusively Go binaries.

Feature-for-feature parity is still closing. The current branch must finish the
remaining graph-surface and end-to-end parity gaps before any new collector
expansion starts.

The rewrite contract for the completed cutover is captured in:

- [Architecture](architecture.md)
- [Architecture Decision Records](adrs/index.md)

The project is now in **Phase 5: Parity Closure**.

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

The Python-to-Go runtime conversion is complete, but full feature parity is not
yet complete.

The branch has met the runtime ownership bar:

- no deployed runtime or write service starts from Python runtime entrypoints
- no Go runtime service imports `go/internal/compatibility/pythonbridge`
- no Python bridge modules exist — `src/` has been deleted entirely
- no parser, discovery, snapshot, content-shaping, recovery, refinalize,
  or admin-repair path depends on Python runtime ownership
- Docker Compose and Helm run the Go-owned platform exclusively
- the Dockerfile is a single Go-only multi-stage build
- the CLI (`pcg`) is a native Go binary using Cobra

The remaining work is tracked in the parity audit and parity-closure plan:

- [Python-To-Go Parity Audit](reference/python-to-go-parity.md)
- `docs/superpowers/plans/2026-04-14-go-parity-closure-plan.md`

## After That

### Phase 5: Parity Closure

Before new collectors begin, close the remaining feature-for-feature parity
gaps in the Go graph and query surfaces.

- finish SQL/dbt lineage maturity
- close language-family graph-surface gaps
- close IaC normalization gaps
- update the docs to reflect the final parity state

### Phase 6: Multi-Collector Expansion

After the Go platform conversion is in place, add new collectors without
changing the core platform contract.

- start with the next source family, likely AWS
- add Kubernetes and other infrastructure collectors on the same scope model
- keep Git, cloud, and data sources aligned through shared reducers
- validate code -> IaC -> cloud -> workload -> data graph flows end to end

That phase should start from the locked rewrite docs, not from fresh design
debates. Future collector work should reuse the scope/generation/fact/reducer
model and the shared operator/admin contract documented in this branch.

### Phase 7: Backend And Scale Validation

Use the rewritten data plane and the first multi-collector workloads to measure
what actually limits scale.

- measure canonical graph write contention
- measure fact-store and queue pressure
- measure reducer throughput and saturation
- decide whether the backend mix still fits the workload
- evaluate alternatives only with real performance evidence

### Phase 8: Collector Framework Maturity

After the first multi-collector proof is stable, harden the collector
framework itself.

- standardize collector onboarding and telemetry
- keep collector families additive instead of special-case
- keep new collectors on the same Go-owned service and data-plane contract
- make new source families follow the same scope/generation/fact/reducer shape

## Longer-term

- Deeper cloud scanning and freshness pipelines
- Stronger semantic resolution and ranking
- Richer environment comparison and blast-radius analysis
- Broader language and IaC coverage
