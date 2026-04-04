"""PostgreSQL-backed content store implementation."""

from __future__ import annotations

import logging
import os
import threading
import time

_logger = logging.getLogger(__name__)
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any

from ..observability import get_observability
from .models import ContentEntityEntry, ContentFileEntry
from .postgres_queries import (
    get_entity_content as postgres_get_entity_content,
    get_file_contents_batch as postgres_get_file_contents_batch,
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

try:
    from psycopg_pool import ConnectionPool as _ConnectionPool
except ImportError:  # pragma: no cover - pool is optional; falls back to single conn.
    _ConnectionPool = None  # type: ignore[assignment,misc]

__all__ = [
    "PostgresContentProvider",
]

DEFAULT_CONTENT_ENTITY_UPSERT_BATCH_SIZE = 500

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


class PostgresContentProvider:
    """Persist and query source content in PostgreSQL."""

    def __init__(self, dsn: str) -> None:
        """Initialize the provider with a connection pool or single-conn fallback.

        Args:
            dsn: PostgreSQL DSN used for both reads and writes.
        """

        self._dsn = dsn
        self._schema_lock = threading.Lock()
        self._initialized = False
        self._pool: Any | None = None
        self._conn: Any | None = None
        self._conn_lock: threading.Lock | None = None

        if psycopg is not None and _ConnectionPool is not None and dsn:
            try:
                _pool_max = int(os.environ.get("PCG_COMMIT_WORKERS", "1")) + 2
                self._pool = _ConnectionPool(
                    dsn,
                    min_size=1,
                    max_size=max(4, _pool_max),
                    kwargs={"autocommit": True, "row_factory": dict_row},
                )
            except Exception:
                _logger.warning(
                    "Connection pool initialization failed, falling back to single connection",
                    exc_info=True,
                )
                self._pool = None
                self._conn_lock = threading.Lock()
        else:
            self._conn_lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        """Return whether the provider can be used in the current process."""

        return psycopg is not None and bool(self._dsn)

    def _ensure_schema(self, conn: Any) -> None:
        """Run schema DDL once across the lifetime of the provider.

        Uses a lightweight existence check before attempting DDL so that
        concurrent writers are never blocked by ``CREATE INDEX IF NOT EXISTS``
        acquiring a ``ShareLock`` on the table.
        """

        if self._initialized:
            return
        with self._schema_lock:
            if not self._initialized:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT 1 FROM information_schema.tables "
                        "WHERE table_schema = 'public' "
                        "AND table_name = 'content_files'"
                    )
                    if cur.fetchone() is not None:
                        self._initialized = True
                        return
                with conn.cursor() as cur:
                    cur.execute(FILE_SCHEMA)
                self._initialized = True

    @contextmanager
    def _cursor(self) -> Any:
        """Yield a dict-row cursor, using the pool when available."""

        if not self.enabled:
            raise RuntimeError(
                "psycopg is not installed or the content store DSN is missing"
            )

        if self._pool is not None:
            with self._pool.connection() as conn:
                self._ensure_schema(conn)
                with conn.cursor() as cursor:
                    yield cursor
        else:
            assert self._conn_lock is not None
            with self._conn_lock:
                if self._conn is None or self._conn.closed:
                    self._conn = psycopg.connect(self._dsn, autocommit=True)
                    self._conn.row_factory = dict_row
                    self._initialized = False
                self._ensure_schema(self._conn)
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
                cursor.execute(_FILE_UPSERT_SQL, _file_entry_params(entry))

    def upsert_file_batch(self, entries: Sequence[ContentFileEntry]) -> None:
        """Insert or update file-content rows via a single ``executemany`` call."""

        if not entries:
            return

        with get_observability().start_span(
            "pcg.content.postgres.upsert_file_batch",
            attributes={
                "pcg.content.file_count": len(entries),
                "pcg.content.repo_id": entries[0].repo_id,
            },
        ):
            rows = [_file_entry_params(e) for e in entries]
            with self._cursor() as cursor:
                cursor.executemany(_FILE_UPSERT_SQL, rows)

    def upsert_entities(
        self,
        entries: Sequence[ContentEntityEntry],
        *,
        entity_batch_size: int | None = None,
    ) -> None:
        """Insert or update entity-content rows.

        Args:
            entries: Entity rows to store.
            entity_batch_size: Override for the per-executemany chunk size.
        """

        if not entries:
            return

        if entity_batch_size is not None:
            batch_size = max(1, min(entity_batch_size, len(entries)))
        else:
            batch_size = _entity_batch_size(len(entries))

        with get_observability().start_span(
            "pcg.content.postgres.upsert_entities",
            attributes={
                "pcg.content.entity_count": len(entries),
                "pcg.content.repo_id": entries[0].repo_id,
            },
        ):
            with self._cursor() as cursor:
                rows = [_entity_entry_params(e) for e in entries]
                for start in range(0, len(rows), batch_size):
                    cursor.executemany(
                        _ENTITY_UPSERT_SQL, rows[start : start + batch_size]
                    )

    def upsert_entities_batch(
        self,
        entries: Sequence[ContentEntityEntry],
        *,
        entity_batch_size: int | None = None,
    ) -> None:
        """Insert or update entity rows from multiple files in one batch."""

        if not entries:
            return

        if entity_batch_size is not None:
            batch_size = max(1, min(entity_batch_size, len(entries)))
        else:
            batch_size = _entity_batch_size(len(entries))

        with get_observability().start_span(
            "pcg.content.postgres.upsert_entities_batch",
            attributes={
                "pcg.content.entity_count": len(entries),
                "pcg.content.repo_id": entries[0].repo_id,
            },
        ):
            rows = [_entity_entry_params(e) for e in entries]
            with self._cursor() as cursor:
                for start in range(0, len(rows), batch_size):
                    cursor.executemany(
                        _ENTITY_UPSERT_SQL, rows[start : start + batch_size]
                    )

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
                hit=False,
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

    def get_file_contents_batch(
        self, *, repo_files: list[dict[str, str]]
    ) -> dict[tuple[str, str], str]:
        """Return indexed file contents for a batch of repo-relative paths."""

        return postgres_get_file_contents_batch(self, repo_files=repo_files)

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
        """Close the connection pool or cached connection when present."""

        if self._pool is not None:
            self._pool.close()
            self._pool = None
            self._initialized = False
        elif self._conn_lock is not None:
            with self._conn_lock:
                if self._conn is not None:
                    self._conn.close()
                    self._conn = None
                    self._initialized = False
