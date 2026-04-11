"""Unit tests for Python ORM-to-SQL extraction helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.python import PythonTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def python_parser() -> PythonTreeSitterParser:
    """Build the real Python parser for ORM-mapping assertions."""

    manager = get_tree_sitter_manager()
    wrapper = MagicMock()
    wrapper.language_name = "python"
    wrapper.language = manager.get_language_safe("python")
    wrapper.parser = manager.create_parser("python")
    return PythonTreeSitterParser(wrapper)


def test_parse_sqlalchemy_tablename_mapping(
    python_parser: PythonTreeSitterParser, temp_test_dir
) -> None:
    """SQLAlchemy ``__tablename__`` assignments should produce table mappings."""

    source_file = temp_test_dir / "models.py"
    source_file.write_text(
        """
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = python_parser.parse(source_file)

    assert result["orm_table_mappings"] == [
        {
            "class_name": "User",
            "table_name": "users",
            "framework": "sqlalchemy",
            "line_number": 9,
        }
    ]


def test_parse_django_meta_db_table_mapping(
    python_parser: PythonTreeSitterParser, temp_test_dir
) -> None:
    """Django ``Meta.db_table`` assignments should produce table mappings."""

    source_file = temp_test_dir / "models.py"
    source_file.write_text(
        """
from django.db import models


class AuditEvent(models.Model):
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "audit.events"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    result = python_parser.parse(source_file)

    assert result["orm_table_mappings"] == [
        {
            "class_name": "AuditEvent",
            "table_name": "audit.events",
            "framework": "django",
            "line_number": 8,
        }
    ]
