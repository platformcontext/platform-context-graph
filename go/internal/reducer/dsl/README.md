# Reducer / DSL

`reducer/dsl` defines the cross-source DSL evaluation seam used by the
reducer and the helpers that turn an `EvaluationResult` into durable
graph-projection phase rows.

## Purpose

Pin two contracts:

1. The accepted DSL reducer scaffold (`RuntimeContract`) - components and
   checkpoints the DSL substrate is expected to own.
2. The runtime evaluator interfaces (`Evaluator`, `DriftEvaluator`) and the
   publication shape (`Publication`, `EvaluationResult`) that bounded DSL
   passes return, plus the helpers that convert and publish them.

## Ownership boundary

- Owns: the DSL scaffold contract, the `Evaluator` and `DriftEvaluator`
  seams, the `Publication`/`EvaluationResult` shape, and the
  result-to-phase-state conversion plus publish helper.
- Does not own: an actual evaluator implementation. The seam is intentionally
  empty here; concrete DSL substrates land elsewhere.
- Does not write to the graph. Phase rows are forwarded through
  `reducer.GraphProjectionPhasePublisher`, which the parent reducer wires.

## Exported surface

Scaffold:

- `PublishedCheckpoint`, `RuntimeContract`, `Validate`,
  `DefaultRuntimeContract`, `RuntimeContractTemplate`.
- The accepted scaffold lists four components - `evaluator`,
  `drift_evaluator`, `deployment_mapping`, `workload_materialization` - and
  five checkpoints (Terraform/cloud/webhook keyspaces at
  `cross_source_anchor_ready`, plus `service_uid` at `deployment_mapping`
  and `workload_materialization`).

Evaluator seam:

- `OutputKind` constants: `OutputKindResolvedRelationship`,
  `OutputKindDriftObservation`.
- `Publication{AcceptanceUnitID, Keyspace, Phase, OutputKind}` plus
  `Validate`.
- `EvaluationResult{Publications}` plus `Validate` and `PhaseStates`.
- `Evaluator` and `DriftEvaluator` interfaces.
- `CanonicalView{ScopeID, GenerationID, CollectorKind}`.
- `PublishEvaluationResult(ctx, publisher, scopeID, generationID, result,
  observedAt) error`.

## Dependencies

- `go/internal/reducer` for `GraphProjectionKeyspace`,
  `GraphProjectionPhase`, `GraphProjectionPhaseKey`,
  `GraphProjectionPhaseState`, and `GraphProjectionPhasePublisher`.

## Telemetry

The package itself does not emit metrics or spans. Callers wrap
`PublishEvaluationResult` with their own telemetry; see
`go/internal/telemetry/instruments.go` for the shared instruments used
elsewhere in the reducer.

## Gotchas / invariants

- This package produces `OutputKindResolvedRelationship` publications, which
  feeds the resolved-relationship row that other reducer domains consume.
  Per CLAUDE.md "Facts-First Bootstrap Ordering", the bootstrap pipeline
  reopens `deployment_mapping` work items in Phase 3 (after backfill) so the
  reducer can produce these rows; any new domain that consumes
  `resolved_relationships` must have its own post-Phase-3 reopen or
  re-trigger and is not entitled to silent ordering from this package.
- `PhaseStates` deduplicates publications that share
  `(AcceptanceUnitID, Keyspace, Phase)` for replay stability and sorts the
  output by `(AcceptanceUnitID, Keyspace, Phase)`.
- `PhaseStates` requires non-blank `scopeID` and `generationID`; a zero
  `observedAt` falls back to `time.Now().UTC()`.
- `PublishEvaluationResult` is a no-op when `publisher` is nil or when the
  result produces zero phase states. It does not synthesize work.
- The `cross_source_anchor_ready` phase is currently reserved for this DSL
  layer and is not produced by canonical projectors; do not publish it from
  outside this package.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/services/resolution-engine.md`
- `go/internal/reducer/aws/README.md`
- `go/internal/reducer/tfstate/README.md`
