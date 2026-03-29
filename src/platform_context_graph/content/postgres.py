"""PostgreSQL-backed content store implementation."""

from __future__ import annotations

import os
import threading
import time
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

from ..observability import get_observability
from .models import ContentEntityEntry, ContentFileEntry
from .postgres_queries import (
    get_entity_content as postgres_get_entity_content,
    get_file_content as postgres_get_file_content,
    search_entity_content as postgres_search_entity_content,
    search_file_content as postgres_search_file_content,
)
from .postgres_support import (
    FILE_SCHEMA,
)

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - exercised when optional dependency missing.
    psycopg = None
    dict_row = None

__all__ = [
    "PostgresContentProvider",
]

DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE = 500


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
            raise RuntimeError(
                "psycopg is not installed or the content store DSN is missing"
            )

        with self._lock:
            if self._conn is None or self._conn.closed:
                self._conn = psycopg.connect(self._dsn, autocommit=True)
                self._conn.row_factory = dict_row
                self._initialized = False
            if not self._initialized:
                with self._conn.cursor() as cursor:
                    cursor.execute(FILE_SCHEMA)
                self._initialized = True
            with self._conn.cursor() as cursor:
                yield cursor

    def upsert_file(self, entry: ContentFileEntry) -> None:
        """Insert or update one file-content row.

        Args:
            entry: File content to store.
        """

        with get_observability().start_span(
            "pcg.content.postgres.upsert_file",
            attributes={
                "pcg.content.repo_id": entry.repo_id,
                "pcg.content.relative_path": entry.relative_path,
            },
        ):
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
                    artifact_type,
                    template_dialect,
                    iac_relevant,
                    indexed_at
                ) VALUES (
                    %(repo_id)s,
                    %(relative_path)s,
                    %(commit_sha)s,
                    %(content)s,
                    %(content_hash)s,
                    %(line_count)s,
                    %(language)s,
                    %(artifact_type)s,
                    %(template_dialect)s,
                    %(iac_relevant)s,
                    %(indexed_at)s
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
                """,
                    {
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
                    },
                )

    def upsert_entities(self, entries: Sequence[ContentEntityEntry]) -> None:
        """Insert or update entity-content rows.

        Args:
            entries: Entity rows to store.
        """

        if not entries:
            return

        raw_batch_size = os.getenv("PCG_CONTENT_ENTITY_UPSERT_BATCH_SIZE")
        try:
            batch_size = max(
                1,
                min(
                    int(raw_batch_size or DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE),
                    len(entries),
                ),
            )
        except ValueError:
            batch_size = min(DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE, len(entries))

        with get_observability().start_span(
            "pcg.content.postgres.upsert_entities",
            attributes={
                "pcg.content.entity_count": len(entries),
                "pcg.content.repo_id": entries[0].repo_id,
            },
        ):
            with self._cursor() as cursor:
                query = """
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
                    artifact_type,
                    template_dialect,
                    iac_relevant,
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
                    %(artifact_type)s,
                    %(template_dialect)s,
                    %(iac_relevant)s,
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
                    artifact_type = EXCLUDED.artifact_type,
                    template_dialect = EXCLUDED.template_dialect,
                    iac_relevant = EXCLUDED.iac_relevant,
                    source_cache = EXCLUDED.source_cache,
                    indexed_at = EXCLUDED.indexed_at
                """
                rows = [
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
                        "artifact_type": entry.artifact_type,
                        "template_dialect": entry.template_dialect,
                        "iac_relevant": entry.iac_relevant,
                        "source_cache": entry.source_cache,
                        "indexed_at": entry.indexed_at,
                    }
                    for entry in entries
                ]
                for start in range(0, len(rows), batch_size):
                    cursor.executemany(query, rows[start : start + batch_size])

    def delete_repository_content(self, repo_id: str) -> None:
        """Delete all cached content rows for one repository.

        Args:
            repo_id: Canonical repository identifier.
        """

        started = time.monotonic()
        success = True
        try:
            with self._cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM content_entities
                    WHERE repo_id = %(repo_id)s
                    """,
                    {"repo_id": repo_id},
                )
                cursor.execute(
                    """
                    DELETE FROM content_files
                    WHERE repo_id = %(repo_id)s
                    """,
                    {"repo_id": repo_id},
                )
        except Exception:
            success = False
            raise
        finally:
            get_observability().record_content_provider_result(
                operation="delete_repository_content",
                backend="postgres",
                success=success,
                hit=True,
                duration_seconds=time.monotonic() - started,
            )

    def get_repository_content_counts(self, *, repo_id: str) -> dict[str, int]:
        """Return file/entity content row counts for one repository."""

        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    (SELECT count(*) FROM content_files WHERE repo_id = %(repo_id)s) AS file_count,
                    (SELECT count(*) FROM content_entities WHERE repo_id = %(repo_id)s) AS entity_count
                """,
                {"repo_id": repo_id},
            )
            row = cursor.fetchone() or {}
        return {
            "content_file_count": int(row.get("file_count") or 0),
            "content_entity_count": int(row.get("entity_count") or 0),
        }

    def get_file_content(
        self, *, repo_id: str, relative_path: str
    ) -> dict[str, Any] | None:
        """Return file content for one repo-relative file path.

        Args:
            repo_id: Canonical repository identifier.
            relative_path: Repo-relative file path.

        Returns:
            Content response mapping when present, otherwise ``None``.
        """

        started = time.monotonic()
        success = True
        result = None
        try:
            result = postgres_get_file_content(
                self,
                repo_id=repo_id,
                relative_path=relative_path,
            )
            return result
        except Exception:
            success = False
            raise
        finally:
            get_observability().record_content_provider_result(
                operation="get_file_content",
                backend="postgres",
                success=success,
                hit=result is not None,
                duration_seconds=time.monotonic() - started,
            )

    def get_entity_content(self, *, entity_id: str) -> dict[str, Any] | None:
        """Return source content for one content-bearing entity.

        Args:
            entity_id: Canonical content entity identifier.

        Returns:
            Entity content response mapping when present, otherwise ``None``.
        """

        started = time.monotonic()
        success = True
        result = None
        try:
            result = postgres_get_entity_content(self, entity_id=entity_id)
            return result
        except Exception:
            success = False
            raise
        finally:
            get_observability().record_content_provider_result(
                operation="get_entity_content",
                backend="postgres",
                success=success,
                hit=result is not None,
                duration_seconds=time.monotonic() - started,
            )

    def search_file_content(
        self,
        *,
        pattern: str,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict[str, Any]:
        """Search indexed file content with optional repository/language filters."""

        started = time.monotonic()
        success = True
        result: dict[str, Any] = {"matches": []}
        try:
            result = postgres_search_file_content(
                self,
                pattern=pattern,
                repo_ids=repo_ids,
                languages=languages,
                artifact_types=artifact_types,
                template_dialects=template_dialects,
                iac_relevant=iac_relevant,
            )
            return result
        except Exception:
            success = False
            raise
        finally:
            get_observability().record_content_provider_result(
                operation="search_file_content",
                backend="postgres",
                success=success,
                hit=bool(result.get("matches")),
                duration_seconds=time.monotonic() - started,
            )

    def search_entity_content(
        self,
        *,
        pattern: str,
        entity_types: list[str] | None = None,
        repo_ids: list[str] | None = None,
        languages: list[str] | None = None,
        artifact_types: list[str] | None = None,
        template_dialects: list[str] | None = None,
        iac_relevant: bool | None = None,
    ) -> dict[str, Any]:
        """Search cached entity snippets with optional filters."""

        started = time.monotonic()
        success = True
        result: dict[str, Any] = {"matches": []}
        try:
            result = postgres_search_entity_content(
                self,
                pattern=pattern,
                entity_types=entity_types,
                repo_ids=repo_ids,
                languages=languages,
                artifact_types=artifact_types,
                template_dialects=template_dialects,
                iac_relevant=iac_relevant,
            )
            return result
        except Exception:
            success = False
            raise
        finally:
            get_observability().record_content_provider_result(
                operation="search_entity_content",
                backend="postgres",
                success=success,
                hit=bool(result.get("matches")),
                duration_seconds=time.monotonic() - started,
            )

    def close(self) -> None:
        """Close the cached PostgreSQL connection when present."""

        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
                self._initialized = False
