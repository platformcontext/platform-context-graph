#!/usr/bin/env python3
"""Support code for the content metadata backfill CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from platform_context_graph.content.templated_detection import (
    ContentMetadata,
    infer_content_metadata,
)

__all__ = [
    "BackfillResult",
    "MetadataUpdate",
    "PostgresBackfillStore",
    "run_backfill",
]


@dataclass(frozen=True, slots=True)
class MetadataUpdate:
    """One metadata update applied to file and entity content rows."""

    repo_id: str
    relative_path: str
    artifact_type: str | None
    template_dialect: str | None
    iac_relevant: bool


@dataclass(frozen=True, slots=True)
class BackfillResult:
    """Summary counters returned by one metadata backfill run."""

    scanned_files: int
    updated_files: int
    updated_entities: int


class ContentMetadataBackfillStore(Protocol):
    """Storage interface used by the backfill runner."""

    def fetch_file_batch(
        self,
        *,
        last_seen: tuple[str, str] | None,
        batch_size: int,
        repo_ids: list[str] | None,
        remaining_limit: int | None,
    ) -> list[dict[str, object]]:
        """Return one ordered batch of file rows to classify."""

    def update_file_metadata(self, updates: list[MetadataUpdate]) -> int:
        """Apply file-row metadata updates and return the changed-row count."""

    def update_entity_metadata(self, updates: list[MetadataUpdate]) -> int:
        """Apply entity-row metadata updates and return the changed-row count."""


class PostgresBackfillStore:
    """PostgreSQL-backed store used by the metadata backfill CLI."""

    def __init__(self, provider: Any) -> None:
        """Initialize the store with one PostgreSQL content provider."""

        self._provider = provider

    def fetch_file_batch(
        self,
        *,
        last_seen: tuple[str, str] | None,
        batch_size: int,
        repo_ids: list[str] | None,
        remaining_limit: int | None,
    ) -> list[dict[str, object]]:
        """Return one ordered batch of file rows to classify and update."""

        filters: list[str] = []
        params: dict[str, object] = {}
        if repo_ids:
            filters.append("repo_id = ANY(%(repo_ids)s)")
            params["repo_ids"] = repo_ids
        if last_seen is not None:
            filters.append("(repo_id, relative_path) > (%(last_repo_id)s, %(last_relative_path)s)")
            params["last_repo_id"] = last_seen[0]
            params["last_relative_path"] = last_seen[1]

        where_clause = ""
        if filters:
            where_clause = f"WHERE {' AND '.join(filters)}"
        limit = batch_size if remaining_limit is None else min(batch_size, remaining_limit)

        with self._provider._cursor() as cursor:
            cursor.execute(
                f"""
                SELECT repo_id, relative_path, content
                FROM content_files
                {where_clause}
                ORDER BY repo_id, relative_path
                LIMIT %(limit)s
                """,
                {**params, "limit": limit},
            )
            return list(cursor.fetchall())

    def update_file_metadata(self, updates: list[MetadataUpdate]) -> int:
        """Update file rows with freshly classified metadata."""

        return self._apply_updates(
            table="content_files",
            updates=updates,
        )

    def update_entity_metadata(self, updates: list[MetadataUpdate]) -> int:
        """Cascade file metadata to entity rows sharing the same path."""

        return self._apply_updates(
            table="content_entities",
            updates=updates,
        )

    def _apply_updates(self, *, table: str, updates: list[MetadataUpdate]) -> int:
        """Apply metadata updates to one table and return changed-row count."""

        if not updates:
            return 0
        if table not in {"content_files", "content_entities"}:
            raise ValueError(f"unsupported metadata backfill table: {table}")

        values_sql_parts: list[str] = []
        params: dict[str, object] = {}
        for index, update in enumerate(updates):
            suffix = f"_{index}"
            values_sql_parts.append(
                f"(%(repo_id{suffix})s, %(relative_path{suffix})s, "
                f"%(artifact_type{suffix})s, %(template_dialect{suffix})s, "
                f"%(iac_relevant{suffix})s)"
            )
            params[f"repo_id{suffix}"] = update.repo_id
            params[f"relative_path{suffix}"] = update.relative_path
            params[f"artifact_type{suffix}"] = update.artifact_type
            params[f"template_dialect{suffix}"] = update.template_dialect
            params[f"iac_relevant{suffix}"] = update.iac_relevant

        with self._provider._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE {table} AS target
                SET artifact_type = source.artifact_type,
                    template_dialect = source.template_dialect,
                    iac_relevant = source.iac_relevant
                FROM (
                    VALUES {", ".join(values_sql_parts)}
                ) AS source(
                    repo_id,
                    relative_path,
                    artifact_type,
                    template_dialect,
                    iac_relevant
                )
                WHERE target.repo_id = source.repo_id
                  AND target.relative_path = source.relative_path
                  AND (
                    target.artifact_type IS DISTINCT FROM source.artifact_type
                    OR target.template_dialect IS DISTINCT FROM source.template_dialect
                    OR target.iac_relevant IS DISTINCT FROM source.iac_relevant
                  )
                """,
                params,
            )
            return cursor.rowcount


def run_backfill(
    *,
    store: ContentMetadataBackfillStore,
    batch_size: int,
    repo_ids: list[str] | None,
    limit: int | None,
    dry_run: bool,
) -> BackfillResult:
    """Run a metadata backfill over existing file rows in ordered batches."""

    scanned_files = 0
    updated_files = 0
    updated_entities = 0
    last_seen: tuple[str, str] | None = None

    while True:
        remaining_limit = None if limit is None else max(limit - scanned_files, 0)
        if remaining_limit == 0:
            break
        batch = store.fetch_file_batch(
            last_seen=last_seen,
            batch_size=batch_size,
            repo_ids=repo_ids,
            remaining_limit=remaining_limit,
        )
        if not batch:
            break

        updates = [_row_to_metadata_update(row) for row in batch]
        scanned_files += len(updates)
        last_row = batch[-1]
        last_seen = (str(last_row["repo_id"]), str(last_row["relative_path"]))

        if dry_run:
            continue

        updated_files += store.update_file_metadata(updates)
        updated_entities += store.update_entity_metadata(updates)

    return BackfillResult(
        scanned_files=scanned_files,
        updated_files=updated_files,
        updated_entities=updated_entities,
    )


def _row_to_metadata_update(row: dict[str, object]) -> MetadataUpdate:
    """Classify one content-files row into a persisted metadata update."""

    metadata: ContentMetadata = infer_content_metadata(
        relative_path=Path(str(row["relative_path"])),
        content=str(row["content"]),
    )
    return MetadataUpdate(
        repo_id=str(row["repo_id"]),
        relative_path=str(row["relative_path"]),
        artifact_type=metadata.artifact_type,
        template_dialect=metadata.template_dialect,
        iac_relevant=metadata.iac_relevant,
    )
