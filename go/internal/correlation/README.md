# Correlation

`correlation` is the entry point for the rule-driven candidate evaluation
pipeline used by the reducer to admit or reject correlation candidates before
canonical materialization.

## Purpose

Aggregate the rule, engine, admission, model, and explain sub-packages, and
expose lightweight reporting helpers (`Summary`, `BuildSummary`) that fold one
`engine.Evaluation` into operator-facing counters.

## Ownership boundary

- Owns: shared evaluation summary shape and the package layout for
  correlation.
- Does not own: rule-pack contents (`rules`), evaluation logic (`engine`),
  admission gating (`admission`), explain rendering (`explain`), or candidate
  types (`model`).
- Does not write to the graph or queue. Callers in `go/internal/reducer/`
  consume `engine.Evaluation` directly to feed projection input loaders.

## Exported surface

- `Summary` - counters for evaluated rules, admitted candidates, rejected
  candidates, conflict count, and low-confidence count.
- `BuildSummary(engine.Evaluation) Summary` - reduces one evaluation pass into
  the counters above; conflict count is sourced from
  `RejectionReasonLostTieBreak` and low-confidence count from
  `RejectionReasonLowConfidence`.

## Dependencies

- `correlation/engine` for `Evaluation` and `Result` shapes.
- `correlation/model` for candidate state and rejection reason constants.

## Telemetry

This package does not emit metrics, spans, or logs. The summary it returns is
plain Go data that callers may attach to their own telemetry (e.g. reducer
status surfaces).

## Gotchas / invariants

- `Summary.EvaluatedRules` reports the count of ordered rule names produced by
  the engine, not the count of rules in the source pack.
- A rejected candidate may carry multiple rejection reasons. `BuildSummary`
  counts each reason occurrence, so a single candidate can increment both
  `LowConfidenceCount` and `ConflictCount`.
- Candidates in `CandidateStateProvisional` are neither admitted nor rejected
  in the summary counters.

## Related docs

- `go/internal/correlation/rules/README.md`
- `go/internal/correlation/engine/README.md`
- `go/internal/correlation/admission/README.md`
- `go/internal/correlation/explain/README.md`
- `go/internal/correlation/model/README.md`
