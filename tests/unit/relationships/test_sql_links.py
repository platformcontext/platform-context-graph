"""Unit tests for SQL relationship materialization."""

from __future__ import annotations

from unittest.mock import Mock

from platform_context_graph.relationships.sql_links import create_all_sql_links


class _FakeResult:
    """Minimal Neo4j-like result object for SQL link lookup tests."""

    def __init__(self, rows: list[dict[str, str]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, str]]:
        """Return all mocked result rows."""

        return list(self._rows)


def test_create_all_sql_links_materializes_sql_edges() -> None:
    """Post-commit SQL materialization should write the expected edge families."""

    session = Mock()
    file_data = [
        {
            "path": "/tmp/sql/schema.sql",
            "classes": [
                {
                    "name": "User",
                    "uid": "content-entity:e_user_class",
                    "line_number": 3,
                }
            ],
            "functions": [
                {
                    "name": "listUsers",
                    "uid": "content-entity:e_list_users",
                    "line_number": 7,
                }
            ],
            "sql_tables": [
                {"name": "public.users", "uid": "content-entity:e_users", "line_number": 1}
            ],
            "sql_columns": [
                {
                    "name": "public.users.id",
                    "uid": "content-entity:e_users_id",
                    "line_number": 2,
                }
            ],
            "sql_views": [
                {
                    "name": "public.active_users",
                    "uid": "content-entity:e_active_users",
                    "line_number": 5,
                }
            ],
            "sql_functions": [
                {
                    "name": "public.touch_updated_at",
                    "uid": "content-entity:e_touch_updated_at",
                    "line_number": 10,
                }
            ],
            "sql_triggers": [
                {
                    "name": "users_touch",
                    "uid": "content-entity:e_users_touch",
                    "line_number": 20,
                }
            ],
            "sql_indexes": [
                {
                    "name": "idx_users_org_id",
                    "uid": "content-entity:e_idx_users_org_id",
                    "line_number": 30,
                }
            ],
            "sql_relationships": [
                {
                    "type": "HAS_COLUMN",
                    "source_name": "public.users",
                    "target_name": "public.users.id",
                    "line_number": 2,
                },
                {
                    "type": "READS_FROM",
                    "source_name": "public.active_users",
                    "target_name": "public.users",
                    "line_number": 6,
                },
                {
                    "type": "TRIGGERS_ON",
                    "source_name": "users_touch",
                    "target_name": "public.users",
                    "line_number": 21,
                },
                {
                    "type": "EXECUTES",
                    "source_name": "users_touch",
                    "target_name": "public.touch_updated_at",
                    "line_number": 21,
                },
                {
                    "type": "INDEXES",
                    "source_name": "idx_users_org_id",
                    "target_name": "public.users",
                    "line_number": 30,
                },
            ],
            "sql_migrations": [
                {
                    "tool": "flyway",
                    "target_kind": "SqlTable",
                    "target_name": "public.users",
                    "line_number": 1,
                }
            ],
            "orm_table_mappings": [
                {
                    "class_name": "User",
                    "table_name": "public.users",
                    "framework": "sqlalchemy",
                    "line_number": 4,
                }
            ],
            "embedded_sql_queries": [
                {
                    "function_name": "listUsers",
                    "table_name": "public.users",
                    "operation": "update",
                    "line_number": 8,
                    "api": "database/sql",
                }
            ],
        }
    ]

    metrics = create_all_sql_links(session, file_data)

    assert metrics["has_column_edges"] == 1
    assert metrics["reads_from_edges"] == 1
    assert metrics["triggers_on_edges"] == 1
    assert metrics["executes_edges"] == 1
    assert metrics["indexes_edges"] == 1
    assert metrics["migrates_edges"] == 1
    assert metrics["maps_to_table_edges"] == 1
    assert metrics["queries_table_edges"] == 1
    assert session.run.call_count == 8


def test_create_all_sql_links_resolves_missing_uids_from_graph() -> None:
    """SQL link materialization should look up graph UIDs when snapshots lack them."""

    session = Mock()

    def _run(query: str, **_kwargs: object) -> _FakeResult | Mock:
        if "MATCH (n:SqlTable)" in query:
            return _FakeResult(
                [
                    {
                        "file_path": "/tmp/sql/schema.sql",
                        "name": "public.users",
                        "line_number": 1,
                        "uid": "content-entity:e_users",
                    }
                ]
            )
        if "MATCH (n:SqlColumn)" in query:
            return _FakeResult(
                [
                    {
                        "file_path": "/tmp/sql/schema.sql",
                        "name": "public.users.id",
                        "line_number": 2,
                        "uid": "content-entity:e_users_id",
                    }
                ]
            )
        return Mock()

    session.run.side_effect = _run
    file_data = [
        {
            "path": "/tmp/sql/schema.sql",
            "sql_tables": [{"name": "public.users", "line_number": 1}],
            "sql_columns": [{"name": "public.users.id", "line_number": 2}],
            "sql_relationships": [
                {
                    "type": "HAS_COLUMN",
                    "source_name": "public.users",
                    "target_name": "public.users.id",
                    "line_number": 2,
                }
            ],
            "sql_migrations": [
                {
                    "tool": "flyway",
                    "target_kind": "SqlTable",
                    "target_name": "public.users",
                    "line_number": 1,
                }
            ],
        }
    ]

    metrics = create_all_sql_links(session, file_data)

    assert metrics["has_column_edges"] == 1
    assert metrics["migrates_edges"] == 1


def test_create_all_sql_links_consumes_write_results() -> None:
    """SQL link writes should eagerly consume Neo4j results so auto-commit finishes."""

    write_result = Mock()
    write_result.data.return_value = []
    write_result.consume = Mock()
    session = Mock()
    session.run.return_value = write_result
    file_data = [
        {
            "path": "/tmp/sql/schema.sql",
            "sql_tables": [
                {"name": "public.users", "uid": "content-entity:e_users", "line_number": 1}
            ],
            "sql_columns": [
                {
                    "name": "public.users.id",
                    "uid": "content-entity:e_users_id",
                    "line_number": 2,
                }
            ],
            "sql_relationships": [
                {
                    "type": "HAS_COLUMN",
                    "source_name": "public.users",
                    "target_name": "public.users.id",
                    "line_number": 2,
                }
            ],
            "sql_migrations": [
                {
                    "tool": "flyway",
                    "target_kind": "SqlTable",
                    "target_name": "public.users",
                    "line_number": 1,
                }
            ],
        }
    ]

    create_all_sql_links(session, file_data)

    assert write_result.consume.call_count == 2


def test_create_all_sql_links_scopes_code_entities_by_file_path() -> None:
    """ORM and embedded-SQL links should not cross-wire duplicate names across files."""

    session = Mock()
    file_data = [
        {
            "path": "/tmp/service_a/models.py",
            "classes": [
                {
                    "name": "User",
                    "uid": "content-entity:e_service_a_user_class",
                    "line_number": 3,
                }
            ],
            "functions": [
                {
                    "name": "loadUsers",
                    "uid": "content-entity:e_service_a_load_users",
                    "line_number": 8,
                }
            ],
            "sql_tables": [
                {
                    "name": "service_a.users",
                    "uid": "content-entity:e_service_a_users",
                    "line_number": 1,
                }
            ],
            "orm_table_mappings": [
                {
                    "class_name": "User",
                    "class_line_number": 3,
                    "table_name": "service_a.users",
                    "framework": "sqlalchemy",
                    "line_number": 4,
                }
            ],
            "embedded_sql_queries": [
                {
                    "function_name": "loadUsers",
                    "function_line_number": 8,
                    "table_name": "service_a.users",
                    "operation": "select",
                    "line_number": 9,
                    "api": "database/sql",
                }
            ],
        },
        {
            "path": "/tmp/service_b/models.py",
            "classes": [
                {
                    "name": "User",
                    "uid": "content-entity:e_service_b_user_class",
                    "line_number": 30,
                }
            ],
            "functions": [
                {
                    "name": "loadUsers",
                    "uid": "content-entity:e_service_b_load_users",
                    "line_number": 40,
                }
            ],
            "sql_tables": [
                {
                    "name": "service_b.users",
                    "uid": "content-entity:e_service_b_users",
                    "line_number": 20,
                }
            ],
            "orm_table_mappings": [
                {
                    "class_name": "User",
                    "class_line_number": 30,
                    "table_name": "service_b.users",
                    "framework": "sqlalchemy",
                    "line_number": 31,
                }
            ],
            "embedded_sql_queries": [
                {
                    "function_name": "loadUsers",
                    "function_line_number": 40,
                    "table_name": "service_b.users",
                    "operation": "select",
                    "line_number": 41,
                    "api": "sqlx",
                }
            ],
        },
    ]

    create_all_sql_links(session, file_data)

    maps_to_table_rows = next(
        call.kwargs["rows"]
        for call in session.run.call_args_list
        if "MAPS_TO_TABLE" in call.args[0]
    )
    queries_table_rows = next(
        call.kwargs["rows"]
        for call in session.run.call_args_list
        if "QUERIES_TABLE" in call.args[0]
    )

    assert maps_to_table_rows == [
        {
            "source_uid": "content-entity:e_service_a_user_class",
            "target_uid": "content-entity:e_service_a_users",
            "line_number": 4,
            "framework": "sqlalchemy",
        },
        {
            "source_uid": "content-entity:e_service_b_user_class",
            "target_uid": "content-entity:e_service_b_users",
            "line_number": 31,
            "framework": "sqlalchemy",
        },
    ]
    assert queries_table_rows == [
        {
            "source_uid": "content-entity:e_service_a_load_users",
            "target_uid": "content-entity:e_service_a_users",
            "line_number": 9,
            "operation": "select",
            "api": "database/sql",
        },
        {
            "source_uid": "content-entity:e_service_b_load_users",
            "target_uid": "content-entity:e_service_b_users",
            "line_number": 41,
            "operation": "select",
            "api": "sqlx",
        },
    ]
