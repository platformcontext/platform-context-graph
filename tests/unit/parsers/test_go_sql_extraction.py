"""Unit tests for Go embedded-SQL extraction helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.go import GoTreeSitterParser
from platform_context_graph.parsers.languages.go_sql_support import _iter_string_literals
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def go_parser() -> GoTreeSitterParser:
    """Build the real Go parser for embedded SQL assertions."""

    manager = get_tree_sitter_manager()
    if not manager.is_language_available("go"):
        pytest.skip("Go tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "go"
    wrapper.language = manager.get_language_safe("go")
    wrapper.parser = manager.create_parser("go")
    return GoTreeSitterParser(wrapper)


def test_parse_embedded_sql_queries_from_database_sql_and_sqlx_calls(
    go_parser: GoTreeSitterParser, temp_test_dir
) -> None:
    """Raw SQL strings should be normalized into table-query hints."""

    source_file = temp_test_dir / "repo.go"
    source_file.write_text(
        """
package repo

import (
    "database/sql"

    "github.com/jmoiron/sqlx"
)

func listUsers(db *sql.DB) error {
    _, err := db.Exec("UPDATE public.users SET email = email WHERE id = $1", 42)
    return err
}

func loadOrgs(db *sqlx.DB) error {
    _, err := db.Queryx("SELECT id FROM public.orgs WHERE id = $1", 42)
    return err
}
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = go_parser.parse(source_file)

    assert result["embedded_sql_queries"] == [
        {
            "function_name": "listUsers",
            "function_line_number": 9,
            "table_name": "public.users",
            "operation": "update",
            "line_number": 10,
            "api": "database/sql",
        },
        {
            "function_name": "loadOrgs",
            "function_line_number": 14,
            "table_name": "public.orgs",
            "operation": "select",
            "line_number": 15,
            "api": "sqlx",
        },
    ]


def test_iter_string_literals_handles_escaped_quotes_in_go_strings() -> None:
    """Interpreted Go strings should not split on escaped double quotes."""

    literals = _iter_string_literals(
        'db.Exec("SELECT id /* \\"audit\\" */ FROM public.users WHERE id = $1", 42)'
    )

    assert literals == [
        ('SELECT id /* \\"audit\\" */ FROM public.users WHERE id = $1', 9)
    ]
