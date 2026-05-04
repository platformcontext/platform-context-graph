# Parser

`parser` owns language adapters, parser registration, SCIP reduction support, and
source-level entity extraction.

Parser changes must preserve fact truth. When a parser emits a new entity,
relationship, or metadata field, update the relevant fixtures, fact contracts,
and downstream docs in the same branch.

## Dependencies

Internal packages: `internal/terraformschema`. The parser registry is
consumed by `internal/collector` and `internal/query`; it does not import
storage, projector, or reducer packages.

## Telemetry

Inherits from `internal/telemetry`; this package does not emit its own
metrics or spans. Parser timing and outcomes are surfaced by callers in
`internal/collector` and `internal/query`.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/local-testing.md`
