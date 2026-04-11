"""Tests for the SQL parser."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.sql import SQLTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def sql_parser() -> SQLTreeSitterParser:
    """Build a SQL parser backed by the real tree-sitter grammar."""

    manager = get_tree_sitter_manager()
    if not manager.is_language_available("sql"):
        pytest.skip("SQL tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "sql"
    wrapper.language = manager.get_language_safe("sql")
    wrapper.parser = manager.create_parser("sql")
    return SQLTreeSitterParser(wrapper)


def test_parse_schema_objects_and_relationship_hints(
    sql_parser: SQLTreeSitterParser, temp_test_dir
) -> None:
    """Parse DDL entities plus the relationship hints needed post-commit."""

    sql_file = temp_test_dir / "schema.sql"
    sql_file.write_text(
        """
CREATE TABLE public.orgs (
  id UUID PRIMARY KEY
);

CREATE TABLE public.users (
  id BIGSERIAL PRIMARY KEY,
  org_id UUID REFERENCES public.orgs(id),
  email TEXT NOT NULL,
  CONSTRAINT fk_org FOREIGN KEY (org_id) REFERENCES public.orgs(id)
);

CREATE VIEW public.active_users AS
SELECT u.id, u.email
FROM public.users u
JOIN public.orgs o ON o.id = u.org_id;

CREATE FUNCTION public.touch_updated_at() RETURNS trigger AS $$
BEGIN
  UPDATE public.users SET email = email WHERE id = NEW.id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_touch BEFORE UPDATE ON public.users
FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

CREATE INDEX idx_users_org_id ON public.users (org_id);
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = sql_parser.parse(sql_file)

    assert result["path"] == str(sql_file)
    assert result["lang"] == "sql"

    assert [item["name"] for item in result["sql_tables"]] == [
        "public.orgs",
        "public.users",
    ]
    assert [item["name"] for item in result["sql_views"]] == ["public.active_users"]
    assert [item["name"] for item in result["sql_functions"]] == [
        "public.touch_updated_at"
    ]
    assert [item["name"] for item in result["sql_triggers"]] == ["users_touch"]
    assert [item["name"] for item in result["sql_indexes"]] == ["idx_users_org_id"]

    column_names = [item["name"] for item in result["sql_columns"]]
    assert "public.orgs.id" in column_names
    assert "public.users.id" in column_names
    assert "public.users.org_id" in column_names
    assert "public.users.email" in column_names

    relationships = result["sql_relationships"]
    assert any(
        item["type"] == "HAS_COLUMN"
        and item["source_name"] == "public.users"
        and item["target_name"] == "public.users.org_id"
        for item in relationships
    )
    assert any(
        item["type"] == "REFERENCES_TABLE"
        and item["source_name"] == "public.users"
        and item["target_name"] == "public.orgs"
        for item in relationships
    )
    assert any(
        item["type"] == "READS_FROM"
        and item["source_name"] == "public.active_users"
        and item["target_name"] == "public.users"
        for item in relationships
    )
    assert any(
        item["type"] == "TRIGGERS_ON"
        and item["source_name"] == "users_touch"
        and item["target_name"] == "public.users"
        for item in relationships
    )
    assert any(
        item["type"] == "EXECUTES"
        and item["source_name"] == "users_touch"
        and item["target_name"] == "public.touch_updated_at"
        for item in relationships
    )
    assert any(
        item["type"] == "INDEXES"
        and item["source_name"] == "idx_users_org_id"
        and item["target_name"] == "public.users"
        for item in relationships
    )


def test_parse_migration_metadata_from_common_layouts(
    sql_parser: SQLTreeSitterParser, temp_test_dir
) -> None:
    """Detect migration metadata and affected SQL objects from the file path."""

    migration_file = (
        temp_test_dir
        / "prisma"
        / "migrations"
        / "20260411_add_users"
        / "migration.sql"
    )
    migration_file.parent.mkdir(parents=True)
    migration_file.write_text(
        """
CREATE TABLE public.users (
  id BIGSERIAL PRIMARY KEY
);

ALTER TABLE public.users ADD COLUMN email TEXT;
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = sql_parser.parse(migration_file)

    assert result["sql_migrations"] == [
        {
            "tool": "prisma",
            "target_kind": "SqlTable",
            "target_name": "public.users",
            "line_number": 1,
        }
    ]


def test_parse_partial_sql_keeps_recoverable_entities(
    sql_parser: SQLTreeSitterParser, temp_test_dir
) -> None:
    """Partial tree-sitter recovery should still emit the entities it can see."""

    sql_file = temp_test_dir / "broken.sql"
    sql_file.write_text(
        """
CREATE TABLE public.users (
  id BIGSERIAL PRIMARY KEY,
  email TEXT

CREATE VIEW public.active_users AS
SELECT id FROM public.users;
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = sql_parser.parse(sql_file)

    assert [item["name"] for item in result["sql_tables"]] == ["public.users"]
    assert [item["name"] for item in result["sql_views"]] == ["public.active_users"]
    assert any(
        item["type"] == "READS_FROM"
        and item["source_name"] == "public.active_users"
        and item["target_name"] == "public.users"
        for item in result["sql_relationships"]
    )
