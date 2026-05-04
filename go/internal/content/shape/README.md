# Content Shape

## Purpose

Translates parser output into the canonical `content.Materialization` shape
the Postgres content writer expects. Centralizes the entity-bucket label
mapping, source_cache snippet derivation, and the bounded byte limits that
keep low-signal entity rows under control.

## Ownership boundary

Owns content shaping only. It consumes parser-emitted file and entity
payloads and produces `content.Materialization` values; it does not touch the
graph, queue, or Postgres directly.

## Exported surface

- `Input`, `File`, and `Entity` value types describing the parser-shaped
  payload.
- `Materialize(input Input) (content.Materialization, error)` — the single
  entry point.

## Dependencies

- `internal/content` for `Materialization`, `EntityRecord`, and
  `CanonicalEntityID`.

## Telemetry

None. Callers (ingester or projector workers) add duration and outcome
metrics around the call.

## Gotchas / invariants

- Bucket order in `contentEntityBuckets` is fixed; reordering changes the
  persisted row order and shows up as diff churn downstream.
- `entityLabelForBucket` rewrites `Module` rows to `ProtocolImplementation`
  when their parser metadata says `module_kind == "protocol_implementation"`.
- `entitySourceCache` prefers parser source for code labels and otherwise
  falls back to a file-body line range, then to `item.Source`.
- `limitEntitySourceCache` truncates oversized entries (currently only
  `Variable` at 4096 bytes) and writes `source_cache_truncated`,
  `source_cache_original_bytes`, and `source_cache_limit_bytes` into entity
  metadata so clients can detect the cut. Truncation is UTF-8 safe.

## Related docs

- `go/internal/content/README.md`
- `docs/docs/architecture.md`
