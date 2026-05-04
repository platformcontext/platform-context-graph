# Collector Discovery

## Purpose

`collector/discovery` resolves the parser-supported files inside a checked-out
repository into a stable, repo-root-relative file set. The git collector calls
it once per snapshot to decide which files to feed the parser registry.

## Ownership boundary

Owns file enumeration and gitignore-aware filtering for the collector. Does
not own snapshotting, parsing, or fact emission — those live in
`internal/collector` and `internal/parser`.

## Exported surface

- `Options` — discovery inputs (root path, ignore rules, supported matcher)
- `PathGlobRule`, `RepoFileSet`, `DiscoveryStats` — shape of a single discovery
  rule, the resolved file set, and per-run statistics
- `SupportedFileMatcher` — predicate the parser registry supplies so
  discovery can skip files no parser claims
- `ResolveRepositoryFileSets`, `ResolveRepositoryFileSetsWithStats` — entry
  points; the `WithStats` variant returns counters operators read from
  `pcg index --discovery-report`

See `doc.go` for the package contract.

## Dependencies

- standard library `io/fs`, `path/filepath`
- `internal/collector` consumes the `RepoFileSet` outputs
- `internal/parser` supplies the `SupportedFileMatcher`

## Telemetry

Discovery does not emit metrics or spans of its own. Counters surface through
the returned `DiscoveryStats` and are reported by the caller (collector) under
`pcg_dp_collector_*` and inside `pcg index --discovery-report` output.

## Gotchas / invariants

- Returned file paths are repo-root-relative and sorted, so downstream stages
  can rely on stable ordering across snapshots.
- Gitignore handling is intentionally conservative: when a `.gitignore` rule
  is ambiguous, discovery includes the file. Downstream parsers reject what
  they cannot handle.
- Per-repo overrides live in `.pcg/discovery.json`. Discovery loads them
  before applying defaults, so repo-local overrides win.

## Related docs

- `docs/docs/reference/local-testing.md`
- `docs/docs/architecture.md` (collector pipeline section)
