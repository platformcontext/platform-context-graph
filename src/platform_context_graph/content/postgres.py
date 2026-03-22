"""PostgreSQL-backed content store implementation."""

from __future__ import annotations

import threading
from collections.abc import Sequence
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from ..utils.debug_log import warning_logger
from .models import ContentEntityEntry, ContentFileEntry

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised when optional dependency missing.
    psycopg = None
    dict_row = None

__all__ = [
    "PostgresContentProvider",
]

_FILE_SCHEMA = """
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
"""


class PostgresContentProvider:
    """Persist and query source content in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Initialize the provider.

        Args:
            dsn: PostgreSQL DSN used for both reads and writes.
        """

        self._dsn = dsn
        self._lock = threading.Lock()
        self._conn: Any | None = None
        self._initialized = False

    @property
    def enabled(self) -> bool:
        """Return whether the provider can be used in the current process."""

        return psycopg is not None and bool(self._dsn)

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor and ensure schema creation on first use."""

        if not self.enabled:
            raise RuntimeError("psycopg is not installed or the content store DSN is missing")

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(_FILE_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_file(self, entry: ContentFileEntry) -> None:
        """Insert or update one file-content row.

        Args:
            entry: File content to store.
        """

        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO content_files (
                    repo_id,
                    relative_path,
                    commit_sha,
                    content,
                    content_hash,
                    line_count,
                    language,
                    indexed_at
                ) VALUES (
                    %(repo_id)s,
                    %(relative_path)s,
                    %(commit_sha)s,
                    %(content)s,
                    %(content_hash)s,
                    %(line_count)s,
                    %(language)s,
                    %(indexed_at)s
                )
                ON CONFLICT (repo_id, relative_path) DO UPDATE
                SET commit_sha = EXCLUDED.commit_sha,
                    content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash,
                    line_count = EXCLUDED.line_count,
                    language = EXCLUDED.language,
                    indexed_at = EXCLUDED.indexed_at
                """,
                {
                    "repo_id": entry.repo_id,
                    "relative_path": entry.relative_path,
                    "commit_sha": entry.commit_sha,
                    "content": entry.content,
                    "content_hash": entry.content_hash,
                    "line_count": entry.line_count,
                    "language": entry.language,
                    "indexed_at": entry.indexed_at,
                },
            )

    def upsert_entities(self, entries: Sequence[ContentEntityEntry]) -> None:
        """Insert or update entity-content rows.

        Args:
            entries: Entity rows to store.
        """

        if not entries:
            return

        with self._cursor() as cursor:
            cursor.executemany(
                """
                INSERT INTO content_entities (
                    entity_id,
                    repo_id,
                    relative_path,
                    entity_type,
                    entity_name,
                    start_line,
                    end_line,
                    start_byte,
                    end_byte,
                    language,
                    source_cache,
                    indexed_at
                ) VALUES (
                    %(entity_id)s,
                    %(repo_id)s,
                    %(relative_path)s,
                    %(entity_type)s,
                    %(entity_name)s,
                    %(start_line)s,
                    %(end_line)s,
                    %(start_byte)s,
                    %(end_byte)s,
                    %(language)s,
                    %(source_cache)s,
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
                    source_cache = EXCLUDED.source_cache,
                    indexed_at = EXCLUDED.indexed_at
                """,
                [
                    {
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
                        "source_cache": entry.source_cache,
                        "indexed_at": entry.indexed_at,
                    }
                    for entry in entries
                ],
            )

    def get_file_content(self, *, repo_id: str, relative_path: str) -> dict[str, Any] | None:
        """Return file content for one repo-relative file path.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.

        Returns:
            Content response mapping when present, otherwise ``None``.
        """

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT repo_id,
                       relative_path,
                       commit_sha,
                       content,
                       content_hash,
                       line_count,
                       language
                FROM content_files
                WHERE repo_id = %(repo_id)s AND relative_path = %(relative_path)s
                """,
                {
                    "repo_id": repo_id,
                    "relative_path": relative_path,
                },
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "available": True,
            "repo_id": row["repo_id"],
            "relative_path": row["relative_path"],
            "content": row["content"],
            "line_count": row["line_count"],
            "language": row["language"],
            "commit_sha": row["commit_sha"],
            "content_hash": row["content_hash"],
            "source_backend": "postgres",
        }

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any] | None:
        """Return source content for one content-bearing entity.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            Entity content response mapping when present, otherwise ``None``.
        """

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT entity_id,
                       repo_id,
                       relative_path,
                       entity_type,
                       entity_name,
                       start_line,
                       end_line,
                       start_byte,
                       end_byte,
                       language,
                       source_cache
                FROM content_entities
                WHERE entity_id = %(entity_id)s
                """,
                {"entity_id": entity_id},
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return {
            "available": True,
            "entity_id": row["entity_id"],
            "repo_id": row["repo_id"],
            "relative_path": row["relative_path"],
            "entity_type": row["entity_type"],
            "entity_name": row["entity_name"],
            "start_line": row["start_line"],
            "end_line": row["end_line"],
            "start_byte": row["start_byte"],
            "end_byte": row["end_byte"],
            "language": row["language"],
            "content": row["source_cache"],
            "source_backend": "postgres",
        }

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search indexed file content with optional repository/language filters."""

        filters = ["content ILIKE %(pattern)s"]
        params: dict[str, Any] = {"pattern": f"%{pattern}%"}
        if repo_ids:
            filters.append("repo_id = ANY(%(repo_ids)s)")
            params["repo_ids"] = repo_ids
        if languages:
            filters.append("language = ANY(%(languages)s)")
            params["languages"] = languages

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT repo_id, relative_path, language, content
                FROM content_files
                WHERE {' AND '.join(filters)}
                ORDER BY repo_id, relative_path
                LIMIT 50
                """,
                params,
            )
            rows = cursor.fetchall()

        return {
            "pattern": pattern,
            "matches": [
                {
                    "repo_id": row["repo_id"],
                    "relative_path": row["relative_path"],
                    "language": row["language"],
                    "snippet": _snippet_for_match(row["content"], pattern),
                    "source_backend": "postgres",
                }
                for row in rows
            ],
        }

    def search_entity_content(
        self,
        *,
        pattern: str,
        entity_types: list[str] | None = None,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
    ) -> dict[str, Any]:
        """Search cached entity snippets with optional filters."""

        filters = ["source_cache ILIKE %(pattern)s"]
        params: dict[str, Any] = {"pattern": f"%{pattern}%"}
        if entity_types:
            filters.append("entity_type = ANY(%(entity_types)s)")
            params["entity_types"] = entity_types
        if repo_ids:
            filters.append("repo_id = ANY(%(repo_ids)s)")
            params["repo_ids"] = repo_ids
        if languages:
            filters.append("language = ANY(%(languages)s)")
            params["languages"] = languages

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT entity_id,
                       repo_id,
                       relative_path,
                       entity_type,
                       entity_name,
                       language,
                       source_cache
                FROM content_entities
                WHERE {' AND '.join(filters)}
                ORDER BY repo_id, relative_path, start_line
                LIMIT 50
                """,
                params,
            )
            rows = cursor.fetchall()

        return {
            "pattern": pattern,
            "matches": [
                {
                    "entity_id": row["entity_id"],
                    "repo_id": row["repo_id"],
                    "relative_path": row["relative_path"],
                    "entity_type": row["entity_type"],
                    "entity_name": row["entity_name"],
                    "language": row["language"],
                    "snippet": _snippet_for_match(row["source_cache"], pattern),
                    "source_backend": "postgres",
                }
                for row in rows
            ],
        }

    def close(self) -> None:
        """Close the cached PostgreSQL connection when present."""

        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
                self._initialized = False


def _snippet_for_match(content: str, pattern: str) -> str:
    """Return a small content snippet centered on the matched pattern.

    Args:
        content: Full content text.
        pattern: Pattern used for matching.

    Returns:
        A bounded snippet for human-readable search results.
    """

    lowered = content.lower()
    index = lowered.find(pattern.lower())
    if index < 0:
        return content[:200]
    start = max(0, index - 80)
    end = min(len(content), index + len(pattern) + 80)
    return content[start:end]
