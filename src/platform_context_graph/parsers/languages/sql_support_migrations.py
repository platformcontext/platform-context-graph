"""Migration-oriented SQL parser helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .sql_support_shared import collect_table_mentions, line_number_for_offset

MIGRATION_LAYOUTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"/prisma/migrations/.+/migration\.sql$", re.IGNORECASE), "prisma"),
    (re.compile(r"/liquibase/", re.IGNORECASE), "liquibase"),
    (re.compile(r"/changelog/", re.IGNORECASE), "liquibase"),
    (re.compile(r"/migrations/.+\.up\.sql$", re.IGNORECASE), "golang-migrate"),
    (re.compile(r"/migrations/", re.IGNORECASE), "generic"),
)
FLYWAY_FILENAME = re.compile(r"(^|/)V\d+__.+\.sql$", re.IGNORECASE)


def detect_migration_tool(path: Path) -> str | None:
    """Return the migration tool implied by a SQL file path, when any."""

    normalized = path.as_posix()
    if FLYWAY_FILENAME.search(normalized):
        return "flyway"
    for pattern, tool in MIGRATION_LAYOUTS:
        if pattern.search(normalized):
            return tool
    return None


def build_migration_entries(
    path: Path,
    source: str,
    results: dict[str, Any],
) -> list[dict[str, Any]]:
    """Return SQL migration metadata rows for a file when it looks like a migration."""

    tool = detect_migration_tool(path)
    if tool is None:
        return []

    entries: list[dict[str, Any]] = []
    seen_targets: set[tuple[str, str]] = set()
    for bucket, kind in (
        ("sql_tables", "SqlTable"),
        ("sql_views", "SqlView"),
        ("sql_functions", "SqlFunction"),
        ("sql_triggers", "SqlTrigger"),
        ("sql_indexes", "SqlIndex"),
    ):
        for item in results.get(bucket, []):
            key = (kind, item["name"])
            if key in seen_targets:
                continue
            seen_targets.add(key)
            entries.append(
                {
                    "tool": tool,
                    "target_kind": kind,
                    "target_name": item["name"],
                    "line_number": item["line_number"],
                }
            )

    for target_name, operation, offset in collect_table_mentions(
        source,
        include_reads=True,
    ):
        if operation not in {
            "select",
            "update",
            "insert",
            "delete",
            "alter",
            "reference",
        }:
            continue
        key = ("SqlTable", target_name)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        entries.append(
            {
                "tool": tool,
                "target_kind": "SqlTable",
                "target_name": target_name,
                "line_number": line_number_for_offset(source, offset),
            }
        )
    entries.sort(
        key=lambda item: (
            item["line_number"],
            item["target_kind"],
            item["target_name"],
        )
    )
    return entries


__all__ = ["build_migration_entries"]
