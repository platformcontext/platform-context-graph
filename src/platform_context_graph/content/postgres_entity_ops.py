"""Entity upsert helpers for the PostgreSQL content provider."""

from __future__ import annotations

import os
from typing import Any

from .models import ContentEntityEntry

DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE = 500

_ENTITY_UPSERT_SQL = """
INSERT INTO content_entities (
    entity_id, repo_id, relative_path, entity_type, entity_name,
    start_line, end_line, start_byte, end_byte, language,
    artifact_type, template_dialect, iac_relevant,
    source_cache, indexed_at
) VALUES (
    %(entity_id)s, %(repo_id)s, %(relative_path)s, %(entity_type)s,
    %(entity_name)s, %(start_line)s, %(end_line)s, %(start_byte)s,
    %(end_byte)s, %(language)s, %(artifact_type)s,
    %(template_dialect)s, %(iac_relevant)s, %(source_cache)s,
    %(indexed_at)s
)
ON CONFLICT (entity_id) DO UPDATE
SET repo_id = EXCLUDED.repo_id,
    relative_path = EXCLUDED.relative_path,
    entity_type = EXCLUDED.entity_type,
    entity_name = EXCLUDED.entity_name,
    start_line = EXCLUDED.start_line,
    end_line = EXCLUDED.end_line,
    start_byte = EXCLUDED.start_byte,
    end_byte = EXCLUDED.end_byte,
    language = EXCLUDED.language,
    artifact_type = EXCLUDED.artifact_type,
    template_dialect = EXCLUDED.template_dialect,
    iac_relevant = EXCLUDED.iac_relevant,
    source_cache = EXCLUDED.source_cache,
    indexed_at = EXCLUDED.indexed_at
"""


def _entity_entry_params(entry: ContentEntityEntry) -> dict[str, Any]:
    """Return the parameter dict for one entity upsert row."""

    return {
        "entity_id": entry.entity_id,
        "repo_id": entry.repo_id,
        "relative_path": entry.relative_path,
        "entity_type": entry.entity_type,
        "entity_name": entry.entity_name,
        "start_line": entry.start_line,
        "end_line": entry.end_line,
        "start_byte": entry.start_byte,
        "end_byte": entry.end_byte,
        "language": entry.language,
        "artifact_type": entry.artifact_type,
        "template_dialect": entry.template_dialect,
        "iac_relevant": entry.iac_relevant,
        "source_cache": entry.source_cache,
        "indexed_at": entry.indexed_at,
    }


def _entity_batch_size(entry_count: int) -> int:
    """Return the clamped entity upsert batch size from configuration."""

    raw = os.getenv("PCG_CONTENT_ENTITY_UPSERT_BATCH_SIZE")
    try:
        return max(
            1,
            min(int(raw or DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE), entry_count),
        )
    except ValueError:
        return min(DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE, entry_count)


def upsert_entity_rows(
    cursor: Any,
    entries: list[ContentEntityEntry],
    *,
    batch_size: int | None = None,
) -> None:
    """Insert or update entity-content rows in bounded executemany chunks."""

    if not entries:
        return

    resolved_batch_size = (
        max(1, min(batch_size, len(entries)))
        if batch_size is not None
        else _entity_batch_size(len(entries))
    )
    rows = [_entity_entry_params(entry) for entry in entries]
    for start in range(0, len(rows), resolved_batch_size):
        cursor.executemany(
            _ENTITY_UPSERT_SQL,
            rows[start : start + resolved_batch_size],
        )


__all__ = [
    "DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE",
    "_ENTITY_UPSERT_SQL",
    "_entity_entry_params",
    "upsert_entity_rows",
]
