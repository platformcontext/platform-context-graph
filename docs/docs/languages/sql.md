# SQL Parser

This page tracks the checked-in Go parser contract for this branch.
Canonical implementation: `go/internal/parser/registry.go` plus the entrypoint and tests listed below.

## Parser Contract
- Language: `sql`
- Family: `language`
- Parser: `DefaultEngine (sql)`
- Entrypoint: `go/internal/parser/sql_language.go`
- Fixture repo: `tests/fixtures/ecosystems/sql_comprehensive/`
- Unit test suite: `go/internal/parser/engine_sql_test.go`
- Integration validation: compose-backed fixture verification (see [Local Testing Runbook](../reference/local-testing.md))

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Tables | `sql-tables` | supported | `sql_tables` | `name, line_number` | `node:SqlTable` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Columns | `sql-columns` | supported | `sql_columns` | `name, line_number` | `node:SqlColumn` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Views | `sql-views` | supported | `sql_views` | `name, line_number` | `node:SqlView` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Functions | `sql-functions` | supported | `sql_functions` | `name, line_number` | `node:SqlFunction` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Triggers | `sql-triggers` | supported | `sql_triggers` | `name, line_number` | `node:SqlTrigger` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Indexes | `sql-indexes` | supported | `sql_indexes` | `name, line_number` | `node:SqlIndex` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| SQL relationships | `sql-relationships` | supported | `sql_relationships` | `type, source_name, target_name, line_number` | `relationship:HAS_COLUMN/REFERENCES_TABLE/READS_FROM/TRIGGERS_ON/EXECUTES/INDEXES` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLSchemaObjectsAndRelationships` | Compose-backed fixture verification | - |
| Migration intelligence | `sql-migrations` | supported | `sql_migrations` | `tool, target_kind, target_name, line_number` | `relationship:MIGRATES` | `go/internal/parser/engine_sql_test.go::TestDefaultEngineParsePathSQLMigrationMetadata` | Compose-backed fixture verification | - |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `unsupported`
- Framework packs: -
- Query surfacing: `supported`
- Real-repo validation: `partial`
- End-to-end indexing: `partial`
- Notes:
  - SQL support is Go-owned end to end for native SQL parsing, migration extraction, embedded SQL link hints, and the JSON-backed dbt and data-intelligence families.
- Real-repo and end-to-end status remain partial because compiled dbt lineage
  still carries explicit unresolved-reference, truly opaque
  templated-expression, complex macro, and derived-expression limits in the
  current Go implementation.
- Row-level aggregate lineage, simple windowed expressions, and simple
  qualified macro wrappers such as `dbt_utils.identity(source.amount)` are now
  tracked in the Go dbt path.
- Nested safe wrappers over those supported row-level forms, such as
  `upper(coalesce(source.segment, 'unknown'))`, are also tracked in the Go dbt
  path.
- The checked-in dbt parity matrix now explicitly proves cast, `date_trunc`,
  `concat`, multi-source `case`, multi-source arithmetic, top-level Jinja
  wrappers around supported lineage-safe expressions, and the key
  unresolved-summary paths in
  `go/internal/parser/dbt_sql_lineage_parity_test.go`.
- The checked-in SQL procedural proof now covers `CREATE OR REPLACE FUNCTION`
  bodies plus legacy `EXECUTE PROCEDURE` trigger wiring in
  `go/internal/parser/sql_parity_test.go`.
- Compiled-model lineage still carries explicit unresolved limits for
  unresolved references, truly opaque templated expressions, complex macros,
  and some derived expressions.

## Go-Owned Data-Intelligence Path

The SQL and analytics runtime on this branch is no longer split with a Python
service path.

- Native SQL parsing and schema-object extraction live in `go/internal/parser/sql_language.go`
- Migration intelligence lives in `go/internal/parser/sql_migrations.go`
- Embedded SQL extraction for Go code lives in `go/internal/parser/go_embedded_sql.go`
- dbt compiled-SQL lineage lives in `go/internal/parser/dbt_sql_lineage.go`
- dbt manifest shaping lives in `go/internal/parser/json_dbt_manifest.go`
- JSON data-intelligence families live in `go/internal/parser/json_data_intelligence.go`


## Known Limitations
- Dialect-specific procedural SQL beyond common Postgres-style bodies may surface only partial table references.
- ALTER/DDL mutation parsing currently prioritizes affected object names over full clause normalization.
- Compiled dbt lineage still records partial coverage for unresolved references,
  templated expressions, complex macro expansion, and some derived
  expressions.
