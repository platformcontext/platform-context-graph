# Reducer / Tags

`reducer/tags` defines the tag-normalization seam and the helpers that
publish canonical-cloud readiness rows once normalization completes.

## Purpose

Pin two contracts:

1. The accepted tag-normalization scaffold (`RuntimeContract`) - the
   `normalizer` component and the `cloud_resource_uid` keyspace it owns.
2. The runtime `Normalizer` seam plus the helpers that turn a
   `NormalizationResult` into durable canonical-cloud phase rows.

## Ownership boundary

- Owns: the scaffold contract, the `Normalizer` seam, and the
  result-to-phase-state conversion plus publish helper.
- Does not own: a concrete tag normalizer. The seam is intentionally empty
  here; the substrate lands elsewhere.
- Does not write to the graph. Phase rows go through
  `reducer.GraphProjectionPhasePublisher`.

## Exported surface

Scaffold:

- `RuntimeContract{Components, CanonicalKeyspaces}` plus `Validate`,
  `DefaultRuntimeContract`, `RuntimeContractTemplate`.
- Accepted scaffold: one component (`normalizer`) and one canonical keyspace
  (`cloud_resource_uid`).

Seam:

- `Normalizer` interface.
- `ObservationBatch{ScopeID, GenerationID, Resources}`.
- `ObservedResource{CanonicalResourceID, RawTags}`.
- `NormalizedResource{CanonicalResourceID, NormalizedTags}`.
- `NormalizationResult{Resources}` plus `Validate` and `PhaseStates`.
- `PublishNormalizationResult(ctx, publisher, scopeID, generationID, result,
  observedAt) error`.

## Dependencies

- `go/internal/reducer` for `GraphProjectionKeyspace`,
  `GraphProjectionPhase`, `GraphProjectionPhaseKey`,
  `GraphProjectionPhaseState`, and `GraphProjectionPhasePublisher`.

## Telemetry

This package does not emit metrics or spans. Callers wrap
`PublishNormalizationResult` with telemetry as needed.

## Gotchas / invariants

- `PhaseStates` always publishes
  `(cloud_resource_uid, canonical_nodes_committed)` per resource. This is a
  Phase 1 (canonical-nodes) publication; downstream domains that consume
  `resolved_relationships` derived from these canonical rows still need the
  standard post-Phase-3 reopen mechanism described in CLAUDE.md "Facts-First
  Bootstrap Ordering". This package does not own that reopen.
- `PhaseStates` deduplicates by `CanonicalResourceID` and sorts the output
  by `AcceptanceUnitID` for replay stability.
- `PhaseStates` requires non-blank `scopeID` and `generationID`; a zero
  `observedAt` falls back to `time.Now().UTC()`.
- `PublishNormalizationResult` is a no-op when `publisher` is nil or when
  the result produces zero phase states.

## Related docs

- `docs/docs/architecture.md`
- `go/internal/reducer/aws/README.md`
- `go/internal/reducer/dsl/README.md`
