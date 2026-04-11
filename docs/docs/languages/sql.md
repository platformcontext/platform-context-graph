# SQL Parser

This file is auto-generated. Do not edit manually.
Canonical source: `src/platform_context_graph/parsers/capabilities/specs/sql.yaml`

## Parser Contract
- Language: `sql`
- Family: `language`
- Parser: `SQLTreeSitterParser`
- Entrypoint: `src/platform_context_graph/parsers/languages/sql.py`
- Fixture repo: `tests/fixtures/ecosystems/sql_comprehensive/`
- Unit test suite: `tests/unit/parsers/test_sql_parser.py`
- Integration test suite: `tests/integration/test_sql_graph.py::TestSqlGraph`

## Capability Checklist
| Capability | ID | Status | Extracted Bucket/Key | Required Fields | Graph Surface | Unit Coverage | Integration Coverage | Rationale |
|-----------|----|--------|------------------------|-----------------|---------------|---------------|----------------------|-----------|
| Tables | `sql-tables` | supported | `sql_tables` | `name, line_number` | `node:SqlTable` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_nodes_are_created` | - |
| Columns | `sql-columns` | supported | `sql_columns` | `name, line_number` | `node:SqlColumn` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_relationships_are_created` | - |
| Views | `sql-views` | supported | `sql_views` | `name, line_number` | `node:SqlView` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_nodes_are_created` | - |
| Functions | `sql-functions` | supported | `sql_functions` | `name, line_number` | `node:SqlFunction` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_nodes_are_created` | - |
| Triggers | `sql-triggers` | supported | `sql_triggers` | `name, line_number` | `node:SqlTrigger` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_nodes_are_created` | - |
| Indexes | `sql-indexes` | supported | `sql_indexes` | `name, line_number` | `node:SqlIndex` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_nodes_are_created` | - |
| SQL relationships | `sql-relationships` | supported | `sql_relationships` | `type, source_name, target_name, line_number` | `relationship:HAS_COLUMN/REFERENCES_TABLE/READS_FROM/TRIGGERS_ON/EXECUTES/INDEXES` | `tests/unit/parsers/test_sql_parser.py::test_parse_schema_objects_and_relationship_hints` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_relationships_are_created` | - |
| Migration intelligence | `sql-migrations` | supported | `sql_migrations` | `tool, target_kind, target_name, line_number` | `relationship:MIGRATES` | `tests/unit/parsers/test_sql_parser.py::test_parse_migration_metadata_from_common_layouts` | `tests/integration/test_sql_graph.py::TestSqlGraph::test_sql_relationships_are_created` | - |

## Support Maturity
- Grammar routing: `supported`
- Normalization: `supported`
- Framework pack status: `unsupported`
- Framework packs: -
- Query surfacing: `supported`
- Real-repo validation: `partial`
- End-to-end indexing: `partial`
- Notes:
  - SQL support is validated through local service repositories with checked-in SQL corpus plus targeted external ORM and Go examples.


## Known Limitations
- Dialect-specific procedural SQL beyond common Postgres-style bodies may surface only partial table references.
- ALTER/DDL mutation parsing currently prioritizes affected object names over full clause normalization.
