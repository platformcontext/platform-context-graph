# Correlation Engine

`correlation/engine` applies a validated rule pack to a candidate slice and
emits deterministic, ordered admission results.

## Purpose

Take one `rules.RulePack` plus a `[]model.Candidate` and return an
`Evaluation` with a stable rule order, per-candidate match counts, and final
candidate states (admitted or rejected) with rejection reasons.

## Ownership boundary

- Owns: rule ordering, per-candidate evaluation loop, tie-breaking among
  admitted candidates that share a `CorrelationKey`, and result sort order.
- Delegates admission gates (confidence and structural requirements) to
  `correlation/admission`.
- Does not own: rule definitions, explain rendering, or graph writes.

## Exported surface

- `Result` - one candidate's evaluated state plus a `MatchCounts` map keyed
  by rule name (populated only for `RuleKindMatch` rules).
- `Evaluation` - `OrderedRuleNames` (post-sort) and `Results` (post-sort).
- `Evaluate(pack rules.RulePack, candidates []model.Candidate) (Evaluation, error)`.

## Dependencies

- `correlation/admission` for the confidence and structural gate.
- `correlation/model` for candidate types.
- `correlation/rules` for the pack schema.

## Telemetry

None. The engine is a pure function; callers attach telemetry around it.

## Gotchas / invariants

- Rules are sorted by `(Priority ascending, Name ascending)` before
  evaluation. Two rules with the same priority sort by name.
- `MatchCounts` are only populated for rules of kind `RuleKindMatch`. The
  count is `min(MaxMatches, len(candidate.Evidence))` when `MaxMatches > 0`;
  if `MaxMatches <= 0`, the count is the full evidence length.
- Tie-break order among admitted candidates sharing a `CorrelationKey`:
  higher `Confidence` wins; on ties, lower `ID` (lexicographic) wins. The
  loser is moved to `CandidateStateRejected` with
  `RejectionReasonLostTieBreak` appended.
- Final result order is `(CorrelationKey, State, ID)`. Within a key, admitted
  candidates sort before rejected candidates.
- `Evaluate` returns an error if the pack fails `Validate` or if any
  candidate fails admission validation. Partial evaluations are not
  returned.

## Related docs

- `go/internal/correlation/admission/README.md`
- `go/internal/correlation/rules/README.md`
- `go/internal/correlation/explain/README.md`
