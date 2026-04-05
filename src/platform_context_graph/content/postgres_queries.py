"""Query helpers for PostgreSQL-backed content retrieval and search."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..observability import trace_query
from ..parsers.languages.templated_detection import infer_content_metadata
from .postgres_support import append_array_filter, snippet_for_match

__all__ = [
    "get_file_contents_batch",
    "get_entity_content",
    "get_file_content",
    "search_entity_content",
    "search_file_content",
]

_SEARCH_PAGE_SIZE = 500
_MAX_SEARCH_SCAN_ROWS = 5_000


def get_file_contents_batch(
    provider: Any,
    *,
    repo_files: list[dict[str, str]],
) -> dict[tuple[str, str], str]:
    """Return file contents for a batch of repo-relative file paths."""

    if not repo_files:
        return {}

    normalized_repo_files = [
        {
            "repo_id": str(row.get("repo_id") or "").strip(),
            "relative_path": str(row.get("relative_path") or "").strip(),
        }
        for row in repo_files
        if str(row.get("repo_id") or "").strip()
        and str(row.get("relative_path") or "").strip()
    ]
    if not normalized_repo_files:
        return {}

    with trace_query(
        "content_postgres_file_batch",
        attributes={"pcg.content.file_count": len(normalized_repo_files)},
    ):
        with provider._cursor() as cursor:
            cursor.execute(
                """
                SELECT repo_id, relative_path, content
                FROM content_files
                WHERE content IS NOT NULL
                  AND (repo_id, relative_path) IN (
                    SELECT repo_id, relative_path
                    FROM unnest(
                        %(repo_ids)s::text[],
                        %(relative_paths)s::text[]
                    ) AS requested(repo_id, relative_path)
                  )
                """,
                {
                    "repo_ids": [row["repo_id"] for row in normalized_repo_files],
                    "relative_paths": [
                        row["relative_path"] for row in normalized_repo_files
                    ],
                },
            )
            rows = cursor.fetchall()
    return {
        (str(row["repo_id"]), str(row["relative_path"])): str(row["content"])
        for row in rows
        if row.get("repo_id") and row.get("relative_path") and row.get("content")
    }


def _resolve_row_metadata(
    *, relative_path: str, content: str, row: dict[str, Any]
) -> dict[str, Any]:
    """Resolve metadata values, inferring them when legacy rows are still null."""

    if not any(
        row.get(key) is None
        for key in ("artifact_type", "template_dialect", "iac_relevant")
    ):
        return {
            "artifact_type": row["artifact_type"],
            "template_dialect": row["template_dialect"],
            "iac_relevant": row["iac_relevant"],
        }
    inferred = infer_content_metadata(
        relative_path=Path(relative_path), content=content
    )
    return {
        "artifact_type": (
            row["artifact_type"]
            if row.get("artifact_type") is not None
            else inferred.artifact_type
        ),
        "template_dialect": (
            row["template_dialect"]
            if row.get("template_dialect") is not None
            else inferred.template_dialect
        ),
        "iac_relevant": (
            row["iac_relevant"]
            if row.get("iac_relevant") is not None
            else inferred.iac_relevant
        ),
    }


def _resolve_entity_row_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """Resolve entity metadata, inheriting from the containing file when available."""

    file_row = {
        "artifact_type": row.get("file_artifact_type"),
        "template_dialect": row.get("file_template_dialect"),
        "iac_relevant": row.get("file_iac_relevant"),
    }
    file_content = row.get("file_content") or row["source_cache"]
    file_metadata = _resolve_row_metadata(
        relative_path=row["relative_path"],
        content=file_content,
        row=file_row,
    )
    return {
        "artifact_type": (
            row["artifact_type"]
            if row.get("artifact_type") is not None
            else file_metadata["artifact_type"]
        ),
        "template_dialect": (
            row["template_dialect"]
            if row.get("template_dialect") is not None
            else file_metadata["template_dialect"]
        ),
        "iac_relevant": (
            row["iac_relevant"]
            if row.get("iac_relevant") is not None
            else file_metadata["iac_relevant"]
        ),
    }


def _matches_metadata_filters(
    *,
    metadata: dict[str, Any],
    artifact_types: list[str] | None,
    template_dialects: list[str] | None,
    iac_relevant: bool | None,
) -> bool:
    """Return whether resolved metadata satisfies the requested filters."""

    if artifact_types and not _matches_artifact_type_filter(
        requested_types=artifact_types,
        resolved_type=metadata["artifact_type"],
    ):
        return False
    if template_dialects and metadata["template_dialect"] not in template_dialects:
        return False
    if iac_relevant is not None and metadata["iac_relevant"] is not iac_relevant:
        return False
    return True


def _matches_artifact_type_filter(
    *, requested_types: list[str], resolved_type: str | None
) -> bool:
    """Return whether one resolved artifact type matches the requested filter.

    Args:
        requested_types: Artifact-type filters supplied by the caller.
        resolved_type: Resolved persisted artifact type for one match candidate.

    Returns:
        ``True`` when the candidate should be included by the artifact-type
        filter.
    """

    if resolved_type in requested_types:
        return True
    return resolved_type is None and "file" in requested_types


def get_file_content(
    provider: Any, *, repo_id: str, relative_path: str
) -> dict[str, Any] | None:
    """Return file content for one repo-relative file path."""

    with trace_query(
        "content_postgres_file",
        attributes={
            "pcg.content.repo_id": repo_id,
            "pcg.content.relative_path": relative_path,
        },
    ):
        with provider._cursor() as cursor:
            cursor.execute(
                """
            SELECT repo_id,
                   relative_path,
                   commit_sha,
                   content,
                   content_hash,
                   line_count,
                   language,
                   artifact_type,
                   template_dialect,
                   iac_relevant
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
    metadata = _resolve_row_metadata(
        relative_path=row["relative_path"],
        content=row["content"],
        row=row,
    )
    return {
        "available": True,
        "repo_id": row["repo_id"],
        "relative_path": row["relative_path"],
        "content": row["content"],
        "line_count": row["line_count"],
        "language": row["language"],
        "artifact_type": metadata["artifact_type"],
        "template_dialect": metadata["template_dialect"],
        "iac_relevant": metadata["iac_relevant"],
        "commit_sha": row["commit_sha"],
        "content_hash": row["content_hash"],
        "source_backend": "postgres",
    }


def get_entity_content(provider: Any, *, entity_id: str) -> dict[str, Any] | None:
    """Return source content for one content-bearing entity."""

    with trace_query(
        "content_postgres_entity",
        attributes={"pcg.content.entity_id": entity_id},
    ):
        with provider._cursor() as cursor:
            cursor.execute(
                """
            SELECT entity_id,
                   ce.repo_id,
                   ce.relative_path,
                   ce.entity_type,
                   ce.entity_name,
                   ce.start_line,
                   ce.end_line,
                   ce.start_byte,
                   ce.end_byte,
                   ce.language,
                   ce.artifact_type,
                   ce.template_dialect,
                   ce.iac_relevant,
                   ce.source_cache,
                   cf.content AS file_content,
                   cf.artifact_type AS file_artifact_type,
                   cf.template_dialect AS file_template_dialect,
                   cf.iac_relevant AS file_iac_relevant
            FROM content_entities ce
            LEFT JOIN content_files cf
              ON cf.repo_id = ce.repo_id
             AND cf.relative_path = ce.relative_path
            WHERE entity_id = %(entity_id)s
            """,
                {"entity_id": entity_id},
            )
            row = cursor.fetchone()
    if row is None:
        return None
    metadata = _resolve_entity_row_metadata(row)
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
        "artifact_type": metadata["artifact_type"],
        "template_dialect": metadata["template_dialect"],
        "iac_relevant": metadata["iac_relevant"],
        "content": row["source_cache"],
        "source_backend": "postgres",
    }


def search_file_content(
    provider: Any,
    *,
    pattern: str,
    repo_ids: list[str] | None = None,
    languages: list[str] | None = None,
    artifact_types: list[str] | None = None,
    template_dialects: list[str] | None = None,
    iac_relevant: bool | None = None,
) -> dict[str, Any]:
    """Search indexed file content with optional repository/language filters."""

    with trace_query(
        "content_postgres_file_search",
        attributes={
            "pcg.content.pattern_length": len(pattern),
            "pcg.content.repo_count": len(repo_ids or []),
        },
    ):
        filters = ["content ILIKE %(pattern)s"]
        params: dict[str, Any] = {"pattern": f"%{pattern}%"}
        append_array_filter(
            filters=filters,
            params=params,
            column="repo_id",
            parameter_name="repo_ids",
            values=repo_ids,
        )
        append_array_filter(
            filters=filters,
            params=params,
            column="language",
            parameter_name="languages",
            values=languages,
        )
        matches = []
        scanned_rows = 0
        offset = 0
        with provider._cursor() as cursor:
            while len(matches) < 50 and scanned_rows < _MAX_SEARCH_SCAN_ROWS:
                cursor.execute(
                    f"""
                SELECT repo_id,
                       relative_path,
                       language,
                       artifact_type,
                       template_dialect,
                       iac_relevant,
                       content
                FROM content_files
                WHERE {' AND '.join(filters)}
                ORDER BY repo_id, relative_path
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                    {
                        **params,
                        "limit": _SEARCH_PAGE_SIZE,
                        "offset": offset,
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    break
                scanned_rows += len(rows)
                for row in rows:
                    metadata = _resolve_row_metadata(
                        relative_path=row["relative_path"],
                        content=row["content"],
                        row=row,
                    )
                    if not _matches_metadata_filters(
                        metadata=metadata,
                        artifact_types=artifact_types,
                        template_dialects=template_dialects,
                        iac_relevant=iac_relevant,
                    ):
                        continue
                    matches.append(
                        {
                            "repo_id": row["repo_id"],
                            "relative_path": row["relative_path"],
                            "language": row["language"],
                            "artifact_type": metadata["artifact_type"],
                            "template_dialect": metadata["template_dialect"],
                            "iac_relevant": metadata["iac_relevant"],
                            "snippet": snippet_for_match(row["content"], pattern),
                            "source_backend": "postgres",
                        }
                    )
                    if len(matches) >= 50:
                        break
                if len(rows) < _SEARCH_PAGE_SIZE:
                    break
                offset += len(rows)

        return {"pattern": pattern, "matches": matches}


def search_entity_content(
    provider: Any,
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

    with trace_query(
        "content_postgres_entity_search",
        attributes={
            "pcg.content.pattern_length": len(pattern),
            "pcg.content.repo_count": len(repo_ids or []),
        },
    ):
        filters = ["source_cache ILIKE %(pattern)s"]
        params: dict[str, Any] = {"pattern": f"%{pattern}%"}
        append_array_filter(
            filters=filters,
            params=params,
            column="ce.entity_type",
            parameter_name="entity_types",
            values=entity_types,
        )
        append_array_filter(
            filters=filters,
            params=params,
            column="ce.repo_id",
            parameter_name="repo_ids",
            values=repo_ids,
        )
        append_array_filter(
            filters=filters,
            params=params,
            column="ce.language",
            parameter_name="languages",
            values=languages,
        )
        matches = []
        scanned_rows = 0
        offset = 0
        with provider._cursor() as cursor:
            while len(matches) < 50 and scanned_rows < _MAX_SEARCH_SCAN_ROWS:
                cursor.execute(
                    f"""
                SELECT entity_id,
                       ce.repo_id,
                       ce.relative_path,
                       ce.entity_type,
                       ce.entity_name,
                       ce.language,
                       ce.artifact_type,
                       ce.template_dialect,
                       ce.iac_relevant,
                       ce.source_cache,
                       cf.content AS file_content,
                       cf.artifact_type AS file_artifact_type,
                       cf.template_dialect AS file_template_dialect,
                       cf.iac_relevant AS file_iac_relevant
                FROM content_entities ce
                LEFT JOIN content_files cf
                  ON cf.repo_id = ce.repo_id
                 AND cf.relative_path = ce.relative_path
                WHERE {' AND '.join(filters)}
                ORDER BY ce.repo_id, ce.relative_path, ce.start_line, ce.entity_id
                LIMIT %(limit)s OFFSET %(offset)s
                """,
                    {
                        **params,
                        "limit": _SEARCH_PAGE_SIZE,
                        "offset": offset,
                    },
                )
                rows = cursor.fetchall()
                if not rows:
                    break
                scanned_rows += len(rows)
                for row in rows:
                    metadata = _resolve_entity_row_metadata(row)
                    if not _matches_metadata_filters(
                        metadata=metadata,
                        artifact_types=artifact_types,
                        template_dialects=template_dialects,
                        iac_relevant=iac_relevant,
                    ):
                        continue
                    matches.append(
                        {
                            "entity_id": row["entity_id"],
                            "repo_id": row["repo_id"],
                            "relative_path": row["relative_path"],
                            "entity_type": row["entity_type"],
                            "entity_name": row["entity_name"],
                            "language": row["language"],
                            "artifact_type": metadata["artifact_type"],
                            "template_dialect": metadata["template_dialect"],
                            "iac_relevant": metadata["iac_relevant"],
                            "snippet": snippet_for_match(row["source_cache"], pattern),
                            "source_backend": "postgres",
                        }
                    )
                    if len(matches) >= 50:
                        break
                if len(rows) < _SEARCH_PAGE_SIZE:
                    break
                offset += len(rows)

        return {"pattern": pattern, "matches": matches}
