# Content

## Purpose

Source-local content write contract for Postgres-backed file and entity
upserts. Lets ingesters and projectors materialize file bodies and parser
entity rows without depending on a specific storage adapter.

## Ownership boundary

Owns the `Writer` port, the materialization and record value types, the
canonical content-entity ID hash, and the runtime tunable for batch width.
Postgres-specific writers and SQL live in `internal/storage/postgres` and
test under `package content_test` in this directory.

## Exported surface

- Write contract: `Writer`, `Materialization`, `Record`, `EntityRecord`,
  `Result`, `MemoryWriter`.
- Identity: `CanonicalEntityID(repoID, relativePath, entityType, entityName,
  lineNumber)`.
- Config: `WriterConfig`, `LoadWriterConfig`, plus
  `ContentEntityBatchSizeEnv` and `MaxContentEntityBatchSize`.

## Dependencies

`golang.org/x/crypto/blake2s` for the entity ID hash. No internal-package
imports.

## Telemetry

None directly. Postgres writer adapters add the duration histograms and
batch counters required by the observability contract.

## Gotchas / invariants

- Tests live in `package content_test` (`postgres_writer_test.go`,
  `writer_test.go`, `writer_config_test.go`); do not move them into
  `package content` without re-checking export visibility.
- `LoadWriterConfig` rejects non-positive integers and values above
  `MaxContentEntityBatchSize` (4000) so the batch stays under the Postgres
  bind-parameter limit.
- `Materialization.Clone` and the per-record `Clone` methods are required
  before retaining inputs in async paths; the writer mutates state in tests.
- `CanonicalEntityID` lower-cases `entityType` and trims whitespace from
  every input before hashing. Callers that pre-trim differently risk ID
  drift.

## Related docs

- `docs/docs/architecture.md`
- `docs/docs/reference/local-testing.md`
