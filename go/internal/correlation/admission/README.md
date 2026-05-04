# Correlation Admission

`correlation/admission` is the confidence-and-structure gate that decides
whether one correlation candidate becomes `CandidateStateAdmitted` or
`CandidateStateRejected`.

## Purpose

Apply two bounded checks against one candidate:

1. confidence >= threshold
2. evidence atoms satisfy every `EvidenceRequirement` (each requirement
   needs at least `MinCount` atoms that match all selectors).

Both must pass for admission. The engine consumes the `Outcome` returned
here to decide which `RejectionReason` (`low_confidence`,
`structural_mismatch`) to attach.

## Ownership boundary

- Owns: the confidence threshold check, the structural evidence check, and
  the resulting state transition for one candidate.
- Does not own: rule ordering, tie-breaking among admitted candidates with
  the same `CorrelationKey`, or explain rendering. Those live in
  `correlation/engine` and `correlation/explain`.

## Exported surface

- `Outcome{MeetsConfidence, MeetsStructure bool}`.
- `Evaluate(candidate model.Candidate, threshold float64,
  requiredEvidence []rules.EvidenceRequirement) (model.Candidate, Outcome, error)`.

## Dependencies

- `correlation/model` for candidate and evidence types.
- `correlation/rules` for `EvidenceField` and `EvidenceRequirement`.

## Telemetry

None. Callers (the engine) attach telemetry as needed.

## Gotchas / invariants

- `threshold` must be in `[0, 1]`. Out-of-range values return an error.
- Selectors are exact-match string comparisons against the chosen
  `EvidenceField` value. Whitespace, case, and prefix differences are not
  normalized.
- The returned candidate is a copy of the input with `State` updated. The
  function does not append `RejectionReasons`; the engine owns that.
- An empty `requiredEvidence` slice always yields `MeetsStructure = true`.

## Related docs

- `go/internal/correlation/engine/README.md`
- `go/internal/correlation/rules/README.md`
- `go/internal/correlation/model/README.md`
