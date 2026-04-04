"""File upsert helpers for the PostgreSQL content provider."""

from __future__ import annotations

import os
from typing import Any
from typing import Sequence

from .models import ContentFileEntry

DEFAULT_CONTENT_FILE_UPSERT_BATCH_SIZE = 500

_FILE_UPSERT_SQL = """
INSERT INTO content_files (
    repo_id, relative_path, commit_sha, content, content_hash,
    line_count, language, artifact_type, template_dialect,
    iac_relevant, indexed_at
) VALUES (
    %(repo_id)s, %(relative_path)s, %(commit_sha)s, %(content)s,
    %(content_hash)s, %(line_count)s, %(language)s, %(artifact_type)s,
    %(template_dialect)s, %(iac_relevant)s, %(indexed_at)s
)
ON CONFLICT (repo_id, relative_path) DO UPDATE
SET commit_sha = EXCLUDED.commit_sha,
    content = EXCLUDED.content,
    content_hash = EXCLUDED.content_hash,
    line_count = EXCLUDED.line_count,
    language = EXCLUDED.language,
    artifact_type = EXCLUDED.artifact_type,
    template_dialect = EXCLUDED.template_dialect,
    iac_relevant = EXCLUDED.iac_relevant,
    indexed_at = EXCLUDED.indexed_at
"""


def _file_entry_params(entry: ContentFileEntry) -> dict[str, Any]:
    """Return the parameter dict for one file upsert row."""

    return {
        "repo_id": entry.repo_id,
        "relative_path": entry.relative_path,
        "commit_sha": entry.commit_sha,
        "content": entry.content,
        "content_hash": entry.content_hash,
        "line_count": entry.line_count,
        "language": entry.language,
        "artifact_type": entry.artifact_type,
        "template_dialect": entry.template_dialect,
        "iac_relevant": entry.iac_relevant,
        "indexed_at": entry.indexed_at,
    }


def _file_batch_size(entry_count: int) -> int:
    """Return the clamped file upsert batch size from configuration."""

    raw = os.getenv("PCG_CONTENT_FILE_UPSERT_BATCH_SIZE")
    try:
        return max(
            1,
            min(int(raw or DEFAULT_CONTENT_FILE_UPSERT_BATCH_SIZE), entry_count),
        )
    except ValueError:
        return min(DEFAULT_CONTENT_FILE_UPSERT_BATCH_SIZE, entry_count)


def upsert_file_batch_rows(
    cursor: Any,
    entries: Sequence[ContentFileEntry],
    *,
    batch_size: int | None = None,
) -> None:
    """Insert or update file-content rows in bounded executemany chunks."""

    if not entries:
        return

    resolved_batch_size = (
        max(1, min(batch_size, len(entries)))
        if batch_size is not None
        else _file_batch_size(len(entries))
    )
    rows = [_file_entry_params(entry) for entry in entries]
    for start in range(0, len(rows), resolved_batch_size):
        cursor.executemany(
            _FILE_UPSERT_SQL,
            rows[start : start + resolved_batch_size],
        )


__all__ = [
    "DEFAULT_CONTENT_FILE_UPSERT_BATCH_SIZE",
    "_FILE_UPSERT_SQL",
    "_file_entry_params",
    "upsert_file_batch_rows",
]
