# IAC Reachability

## Purpose

Classifies discovered Terraform, Helm, Ansible, and Compose artifacts as in
use, candidate dead, or ambiguous from bounded repository content evidence.
Powers the cleanup-truth surface that flags unused IaC.

## Ownership boundary

See `doc.go` for the canonical contract paragraph. This package consumes
indexed file content already shaped by upstream collectors and produces
reachability rows; it does not read repos, render templates, or write graph
nodes.

## Exported surface

- `Reachability` (`used`, `unused`, `ambiguous`) and `Finding`
  (`in_use`, `candidate_dead_iac`, `ambiguous_dynamic_reference`) enums.
- `File`, `Options`, `Row` value types.
- `Analyze(filesByRepo, opts)` — main entry point.
- `CleanupRows(rows, includeAmbiguous)` — operator-facing filter.
- `FamilyFilter(families)` and `RelevantFile(relativePath)` for caller-side
  pre-filtering.

## Dependencies

- `gopkg.in/yaml.v3` for Compose document parsing.

## Telemetry

None directly. Upstream callers (the cleanup-truth handler) own metrics.

## Gotchas / invariants

- Confidence values are fixed: 0.99 for `in_use`, 0.75 for
  `candidate_dead_iac`, 0.40 for `ambiguous_dynamic_reference`. Changing
  them affects operator ranking.
- Ambiguous rows are only included when `Options.IncludeAmbiguous` is true.
  Ambiguity is the "we found a templated reference we cannot statically
  resolve" signal, not "we did not look hard enough."
- `RelevantFile` is the cheap pre-filter callers should use before passing
  files in. Anything off the supported extension list is silently ignored.
- Compose service detection looks at `services:` keys in
  `compose.yaml`/`docker-compose.yaml` and at `docker compose <command>`
  invocations in shell-like content.
- Output rows are sorted by ID for deterministic diffs in tests.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/http-api.md` (cleanup-truth surface)
