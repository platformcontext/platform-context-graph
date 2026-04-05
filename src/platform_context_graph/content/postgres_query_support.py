"""Support helpers for PostgreSQL-backed content queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..parsers.languages.templated_detection import infer_content_metadata


def resolve_row_metadata(
    *, relative_path: str, content: str, row: dict[str, Any]
) -> dict[str, Any]:
    """Resolve metadata values, inferring them when legacy rows are still null.

    Args:
        relative_path: Repo-relative file path for the content row.
        content: Raw file content used for metadata inference.
        row: Persisted metadata row from Postgres.

    Returns:
        Resolved metadata values, combining stored and inferred fields.
    """

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


def resolve_entity_row_metadata(row: dict[str, Any]) -> dict[str, Any]:
    """Resolve entity metadata, inheriting from the containing file when needed.

    Args:
        row: Persisted entity row from Postgres.

    Returns:
        Resolved metadata values for the entity.
    """

    file_row = {
        "artifact_type": row.get("file_artifact_type"),
        "template_dialect": row.get("file_template_dialect"),
        "iac_relevant": row.get("file_iac_relevant"),
    }
    file_content = row.get("file_content") or row["source_cache"]
    file_metadata = resolve_row_metadata(
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


def matches_artifact_type_filter(
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


def matches_metadata_filters(
    *,
    metadata: dict[str, Any],
    artifact_types: list[str] | None,
    template_dialects: list[str] | None,
    iac_relevant: bool | None,
) -> bool:
    """Return whether resolved metadata satisfies the requested filters.

    Args:
        metadata: Resolved metadata for one file or entity row.
        artifact_types: Optional artifact-type filters from the caller.
        template_dialects: Optional template dialect filters from the caller.
        iac_relevant: Optional IaC relevance filter from the caller.

    Returns:
        ``True`` when the row matches all active filters.
    """

    if artifact_types and not matches_artifact_type_filter(
        requested_types=artifact_types,
        resolved_type=metadata["artifact_type"],
    ):
        return False
    if template_dialects and metadata["template_dialect"] not in template_dialects:
        return False
    if iac_relevant is not None and metadata["iac_relevant"] is not iac_relevant:
        return False
    return True
