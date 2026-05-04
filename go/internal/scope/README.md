# Scope

## Purpose

Durable identity for ingestion scopes and the lifecycle of their generations.
Used everywhere a collector, projector, or reducer needs to talk about "what
source produced this fact and which snapshot of that source did it come from."

## Ownership boundary

Owns scope identity, collector-kind enums, and generation-status transitions.
Storage rows for scopes and generations live in `internal/storage/postgres`
and use these contracts as their value shape.

## Exported surface

- `ScopeKind`, `CollectorKind`, `TriggerKind`, `GenerationStatus` enums and
  their `Validate` / `IsTerminal` methods.
- `IngestionScope` with `Validate`, `MetadataCopy`, `HasPriorGeneration`.
- `ScopeGeneration` with `Validate`, `ValidateForScope`, `IsTerminal`,
  `CanTransitionTo`, `TransitionTo`, `MarkActive`, `MarkCompleted`,
  `MarkSuperseded`, `MarkFailed`.

## Dependencies

Standard library only.

## Telemetry

None.

## Gotchas / invariants

- Allowed transitions are listed in `allowedGenerationTransitions`. Pending
  may move to active or failed; active may move to superseded, completed, or
  failed; the three terminal states do not move.
- `PreviousGenerationExists` is the reliable "skip cleanup" gate. The
  `ActiveGenerationID` field is not — a failed first generation may leave no
  active generation despite the scope having a prior generation row.
- `ScopeGeneration.IngestedAt` must not precede `ObservedAt`.
- `MetadataCopy` returns nil for empty maps. Callers that need a non-nil
  empty map must allocate their own.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/deployment/service-runtimes.md`
