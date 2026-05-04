# Workflow

## Purpose

Durable contracts for the workflow control plane. Defines the value types,
status enums, validation rules, fairness scheduler, and reducer-facing phase
contract that the coordinator, ingester collectors, and storage layer all share.

## Ownership boundary

Owns workflow runs, work items, claims, desired and durable collector
instances, completeness states, and the per-collector-kind phase contract.
Storage rows live in `internal/storage/postgres`; the coordinator loop lives
in `internal/coordinator`. This package never opens database connections.

## Exported surface

- Status enums: `CollectorMode`, `TriggerKind`, `RunStatus`,
  `WorkItemStatus`, `ClaimStatus`.
- Durable values: `Run`, `WorkItem`, `Claim`, `DesiredCollectorInstance`,
  `CollectorInstance`, `CompletenessState`.
- Phase contract: `PhaseRequirement`, `PhasePublicationKey`, plus
  `CollectorContractFor`, `CanonicalKeyspacesForCollector`,
  `RequiredPhasesForCollector`.
- Run progress: `CollectorRunProgress`, `RunProgressSnapshot`,
  `ReconcileRunProgress`, completeness status constants.
- Claims and store: `ClaimSelector`, `ClaimMutation`, `ClaimedWorkItem`,
  `ControlStore`.
- Fairness: `FairnessCandidate`, `ClaimTarget`, `FamilyFairnessScheduler`,
  `NewFamilyFairnessScheduler`, `FairnessCandidatesFromCollectorInstances`.
- Defaults: `DefaultClaimLeaseTTL`, `DefaultHeartbeatInterval`,
  `DefaultReapInterval`, `DefaultExpiredClaimLimit`,
  `DefaultExpiredClaimRequeueDelay`.

## Dependencies

- `internal/scope` for `CollectorKind`.
- `internal/reducer` for keyspace and phase identifiers used by the contract.

## Telemetry

None. Coordinator and storage layers own telemetry around these contracts.

## Gotchas / invariants

- Every `Validate` enforces non-empty identifiers, known status values, and
  `updated_at >= created_at`. Stored rows that fail validation should be
  treated as corruption.
- `ReconcileRunProgress` uses deterministic ordering for completeness rows;
  callers can compare snapshots for drift.
- `FamilyFairnessScheduler.Next` mutates internal weight state, so a single
  scheduler instance is not safe for concurrent use.
- Adding a new collector family requires updating `collectorContracts` in
  `collector_contract.go`; the coordinator and storage layers consume the
  table via the `RequiredPhasesForCollector` lookup.

## Related docs

- `docs/docs/deployment/service-runtimes.md`, `docs/docs/architecture.md`,
  `go/internal/coordinator/README.md`
