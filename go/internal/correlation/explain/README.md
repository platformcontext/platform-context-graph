# Correlation Explain

`correlation/explain` formats one `engine.Result` as a stable text block for
the explain API.

## Purpose

Render the candidate header, match counts, rejection reasons, and evidence
atoms in a deterministic order so explain output is comparable across runs
and replay-stable.

## Ownership boundary

- Owns: the text format and sort order of explain output.
- Does not own: evaluation, admission, or candidate identity. The engine
  must already have decided the candidate's state and reasons before
  `Render` is called.

## Exported surface

- `Render(result engine.Result) string`.

## Dependencies

- `correlation/engine` for `Result`.
- `correlation/model` for `EvidenceAtom`.

## Telemetry

None.

## Gotchas / invariants

- Output line order: header, then match-count lines sorted by rule name,
  then rejection-reason lines sorted alphabetically, then evidence lines
  sorted by `(ID, SourceSystem, EvidenceType)`.
- Header format is `candidate=<id> kind=<kind> key=<correlation_key>
  state=<state> confidence=<%.2f>`. Confidence is rendered to two decimal
  places; callers needing higher precision must format outside Render.
- Match-count lines are emitted only for keys present in
  `Result.MatchCounts`; the engine populates that map only for
  `RuleKindMatch` rules.
- The function returns lines joined by `\n`; there is no trailing newline.

## Related docs

- `go/internal/correlation/engine/README.md`
- `go/internal/correlation/README.md`
