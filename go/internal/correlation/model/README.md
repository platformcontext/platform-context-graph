# Correlation Model

`correlation/model` holds the shared types every other correlation sub-package
imports: candidates, evidence atoms, candidate states, and rejection reasons.

## Purpose

Define the in-memory representation of a correlation candidate and its
supporting evidence so that rule packs, the engine, admission, and explain
all agree on the same identity, state machine, and confidence contract.

## Ownership boundary

- Owns: `Candidate`, `EvidenceAtom`, `CandidateState`, `RejectionReason`, and
  their `Validate` methods.
- Does not own: rule schemas (`rules`), evaluation flow (`engine`), gating
  logic (`admission`), or rendering (`explain`).

## Exported surface

- `CandidateState` constants: `CandidateStateProvisional`,
  `CandidateStateAdmitted`, `CandidateStateRejected`.
- `RejectionReason` constants: `RejectionReasonLowConfidence`,
  `RejectionReasonStructuralMismatch`, `RejectionReasonLostTieBreak`.
- `Candidate` and `EvidenceAtom` structs, each with a `Validate` method.

## Dependencies

Standard library only (`fmt`, `strings`).

## Telemetry

None. Pure data types.

## Gotchas / invariants

- `Candidate.Confidence` and `EvidenceAtom.Confidence` must be in `[0, 1]`.
- `Candidate.ID`, `Kind`, and `CorrelationKey` must be non-blank;
  `EvidenceAtom.ID`, `SourceSystem`, `EvidenceType`, `ScopeID`, and `Key` must
  be non-blank. `Validate` rejects whitespace-only values.
- `CandidateStateProvisional` is the pre-evaluation state. The engine never
  emits provisional candidates as final results; admission must move the
  candidate to admitted or rejected.

## Related docs

- `go/internal/correlation/README.md`
- `go/internal/correlation/admission/README.md`
- `go/internal/correlation/engine/README.md`
