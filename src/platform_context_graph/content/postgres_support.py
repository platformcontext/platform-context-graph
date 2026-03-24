"""Shared PostgreSQL content-store schema and query helpers."""

from __future__ import annotations

from typing import Any

__all__ = [
    "FILE_SCHEMA",
    "append_array_filter",
    "append_bool_filter",
    "snippet_for_match",
]

FILE_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS content_files (
    repo_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    commit_sha TEXT,
    content TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    line_count INTEGER NOT NULL,
    language TEXT,
    indexed_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (repo_id, relative_path)
);

ALTER TABLE content_files ADD COLUMN IF NOT EXISTS artifact_type TEXT;
ALTER TABLE content_files ADD COLUMN IF NOT EXISTS template_dialect TEXT;
ALTER TABLE content_files ADD COLUMN IF NOT EXISTS iac_relevant BOOLEAN;

CREATE TABLE IF NOT EXISTS content_entities (
    entity_id TEXT PRIMARY KEY,
    repo_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_name TEXT NOT NULL,
    start_line INTEGER NOT NULL,
    end_line INTEGER NOT NULL,
    start_byte INTEGER,
    end_byte INTEGER,
    language TEXT,
    source_cache TEXT NOT NULL,
    indexed_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE content_entities ADD COLUMN IF NOT EXISTS artifact_type TEXT;
ALTER TABLE content_entities ADD COLUMN IF NOT EXISTS template_dialect TEXT;
ALTER TABLE content_entities ADD COLUMN IF NOT EXISTS iac_relevant BOOLEAN;

CREATE INDEX IF NOT EXISTS content_files_repo_path_idx
    ON content_files (repo_id, relative_path);
CREATE INDEX IF NOT EXISTS content_entities_repo_idx
    ON content_entities (repo_id);
CREATE INDEX IF NOT EXISTS content_entities_type_idx
    ON content_entities (entity_type);
CREATE INDEX IF NOT EXISTS content_entities_path_idx
    ON content_entities (relative_path);
CREATE INDEX IF NOT EXISTS content_files_content_trgm_idx
    ON content_files USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS content_entities_source_trgm_idx
    ON content_entities USING gin (source_cache gin_trgm_ops);
CREATE INDEX IF NOT EXISTS content_files_artifact_type_idx
    ON content_files (artifact_type);
CREATE INDEX IF NOT EXISTS content_files_template_dialect_idx
    ON content_files (template_dialect);
CREATE INDEX IF NOT EXISTS content_files_iac_relevant_idx
    ON content_files (iac_relevant);
CREATE INDEX IF NOT EXISTS content_entities_artifact_type_idx
    ON content_entities (artifact_type);
CREATE INDEX IF NOT EXISTS content_entities_template_dialect_idx
    ON content_entities (template_dialect);
CREATE INDEX IF NOT EXISTS content_entities_iac_relevant_idx
    ON content_entities (iac_relevant);
"""


def append_array_filter(
    *,
    filters: list[str],
    params: dict[str, Any],
    column: str,
    parameter_name: str,
    values: list[str] | None,
) -> None:
    """Append an ``ANY`` filter when non-empty values are provided."""

    if values:
        filters.append(f"{column} = ANY(%({parameter_name})s)")
        params[parameter_name] = values


def append_bool_filter(
    *,
    filters: list[str],
    params: dict[str, Any],
    column: str,
    parameter_name: str,
    value: bool | None,
) -> None:
    """Append an equality filter when a tri-state boolean is provided."""

    if value is not None:
        filters.append(f"{column} = %({parameter_name})s")
        params[parameter_name] = value


def snippet_for_match(content: str, pattern: str) -> str:
    """Return a small content snippet centered on the matched pattern."""

    lowered = content.lower()
    index = lowered.find(pattern.lower())
    if index < 0:
        return content[:200]
    start = max(0, index - 80)
    end = min(len(content), index + len(pattern) + 80)
    return content[start:end]
