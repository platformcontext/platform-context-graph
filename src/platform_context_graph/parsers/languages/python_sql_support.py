"""SQL-aware helper extraction for Python parser results."""

from __future__ import annotations

import ast
from typing import Any


def extract_python_sql_mappings(source_code: str) -> list[dict[str, Any]]:
    """Return ORM table mappings inferred from Python source code."""

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return []

    mappings: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        sqlalchemy_mapping = _extract_sqlalchemy_mapping(node)
        if sqlalchemy_mapping is not None:
            mappings.append(sqlalchemy_mapping)
        django_mapping = _extract_django_mapping(node)
        if django_mapping is not None:
            mappings.append(django_mapping)
    return mappings


def _extract_sqlalchemy_mapping(node: ast.ClassDef) -> dict[str, Any] | None:
    """Return one SQLAlchemy ``__tablename__`` mapping when present."""

    for child in node.body:
        if not isinstance(child, ast.Assign):
            continue
        for target in child.targets:
            if isinstance(target, ast.Name) and target.id == "__tablename__":
                value = _constant_string(child.value)
                if value is None:
                    return None
                return {
                    "class_name": node.name,
                    "table_name": value,
                    "framework": "sqlalchemy",
                    "line_number": child.lineno,
                }
    return None


def _extract_django_mapping(node: ast.ClassDef) -> dict[str, Any] | None:
    """Return one Django ``Meta.db_table`` mapping when present."""

    for child in node.body:
        if not isinstance(child, ast.ClassDef) or child.name != "Meta":
            continue
        for meta_child in child.body:
            if not isinstance(meta_child, ast.Assign):
                continue
            for target in meta_child.targets:
                if isinstance(target, ast.Name) and target.id == "db_table":
                    value = _constant_string(meta_child.value)
                    if value is None:
                        return None
                    return {
                        "class_name": node.name,
                        "table_name": value,
                        "framework": "django",
                        "line_number": meta_child.lineno,
                    }
    return None


def _constant_string(node: ast.AST) -> str | None:
    """Return the string literal represented by one AST node, when possible."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


__all__ = ["extract_python_sql_mappings"]
