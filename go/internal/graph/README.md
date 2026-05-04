# Graph

## Purpose

Source-local graph write contract plus the Cypher builders, batch UNWIND
helpers, deletion mutations, and schema bootstrap shared by every backend
adapter. Backend dialect differences stay narrow and explicit here.

## Ownership boundary

Owns the `Writer` port, canonical entity merge builders, batched UNWIND
helpers, file and repository subtree mutations, and the EnsureSchema
constraint and index contract. Backend-specific drivers live under
`internal/storage/neo4j` and the NornicDB adapter; backend-neutral write
contracts live under `internal/storage/cypher`.

## Exported surface

- Write contract: `Writer`, `Materialization`, `Record`, `Result`,
  `MemoryWriter`.
- Cypher seam: `CypherStatement`, `CypherExecutor`.
- Entity merges: `EntityProps`, `BuildEntityMergeStatement`, `MergeEntity`,
  `ValidateCypherLabel`, `ValidateCypherPropertyKeys`.
- Batch UNWIND: `BatchEntityRow`, `BatchFileRow`, `BatchRelationshipRow`,
  `BatchMergeEntities`, `BatchMergeFiles`, `BatchMergeRelationships`,
  `DefaultBatchSize`.
- Mutations: `DeleteFileFromGraph`, `DeleteRepositoryFromGraph`, `ResetRepositorySubtreeInGraph`.
- Schema: `SchemaBackend` (`neo4j`, `nornicdb`), `SchemaStatements`,
  `SchemaStatementsForBackend`, `EnsureSchema`, `EnsureSchemaWithBackend`.

## Dependencies

Standard library plus `log/slog`. No internal-package imports.

## Telemetry

`EnsureSchema` logs warnings via `slog` when an individual statement fails and
keeps going so partial failures leave the schema in a documented state. No
metric or trace instruments are registered here; backend executors own those.

## Gotchas / invariants

- `cypherSafePattern` rejects labels and property keys outside
  `[a-zA-Z_][a-zA-Z0-9_]*`. Callers passing dynamic values must validate
  first; the builders return errors otherwise.
- `BatchMergeEntities` splits rows into UID-identity and name-identity groups
  so MERGE clauses can hit indexes directly. All rows in a single call must
  share `Label`.
- `BatchMergeRelationships` requires every row to share source label, target
  label, and relationship type.
- `Module` uses an index, not a uniqueness constraint, because canonical
  imports MERGE on shared `name` while semantic merges use per-repo `uid`.
- The schema contract is the checked-in truth for graph node and full-text
  index shape. Changes here must update the active ADR chunk status.

## Related docs

- `docs/docs/architecture.md`,
  `docs/docs/adrs/2026-04-22-nornicdb-graph-backend-candidate.md`,
  `go/internal/storage/cypher/README.md`
