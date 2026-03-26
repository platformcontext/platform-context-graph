"""Durable repository coverage helpers."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from ...runtime.status_store import (
    get_repository_coverage as get_runtime_repository_coverage,
    list_repository_coverage as list_runtime_repository_coverage,
)

__all__ = [
    "coverage_summary_from_row",
    "coverage_gaps_from_row",
    "coverage_limitations_from_row",
    "get_repository_coverage_payload",
    "list_repository_coverage_payload",
]


def _normalize_value(value: Any) -> Any:
    """Return a JSON-serializable coverage field value."""

    if isinstance(value, datetime):
        return value.isoformat()
    return value


def coverage_gaps_from_row(row: dict[str, Any] | None) -> dict[str, int | str]:
    """Return completeness and gap counters for one persisted coverage row."""

    if row is None:
        return {
            "completeness_state": "failed",
            "graph_gap_count": 0,
            "content_gap_count": 0,
        }
    discovered_file_count = int(row.get("discovered_file_count") or 0)
    graph_recursive_file_count = int(row.get("graph_recursive_file_count") or 0)
    content_file_count = int(row.get("content_file_count") or 0)
    graph_gap_count = max(discovered_file_count - graph_recursive_file_count, 0)
    content_gap_count = max(graph_recursive_file_count - content_file_count, 0)
    status = str(row.get("status") or "").lower()
    finalization_status = str(row.get("finalization_status") or "").lower()

    completeness_state = "complete"
    if status == "failed" or finalization_status == "failed":
        completeness_state = "failed"
    elif graph_gap_count > 0:
        completeness_state = "graph_partial"
    elif content_gap_count > 0:
        completeness_state = "content_partial"

    return {
        "completeness_state": completeness_state,
        "graph_gap_count": graph_gap_count,
        "content_gap_count": content_gap_count,
    }


def coverage_summary_from_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    """Project a concise repository coverage summary from one persisted row."""

    if row is None:
        return None
    gaps = coverage_gaps_from_row(row)
    return {
        "run_id": row.get("run_id"),
        "index_status": row.get("status"),
        "phase": row.get("phase"),
        "finalization_status": row.get("finalization_status"),
        "graph_available": bool(row.get("graph_available")),
        "server_content_available": bool(row.get("server_content_available")),
        "discovered_file_count": int(row.get("discovered_file_count") or 0),
        "graph_recursive_file_count": int(row.get("graph_recursive_file_count") or 0),
        "content_file_count": int(row.get("content_file_count") or 0),
        "content_entity_count": int(row.get("content_entity_count") or 0),
        "root_file_count": int(row.get("root_file_count") or 0),
        "root_directory_count": int(row.get("root_directory_count") or 0),
        "top_level_functions": int(row.get("top_level_function_count") or 0),
        "class_methods": int(row.get("class_method_count") or 0),
        "functions": int(row.get("total_function_count") or 0),
        "classes": int(row.get("class_count") or 0),
        "last_error": _normalize_value(row.get("last_error")),
        "updated_at": _normalize_value(row.get("updated_at")),
        "limitations": coverage_limitations_from_row(row),
        **gaps,
    }


def coverage_limitations_from_row(row: dict[str, Any] | None) -> list[str]:
    """Return stable coverage limitation codes for a persisted row."""

    if row is None:
        return ["graph_partial", "content_partial"]

    limitations: list[str] = []
    gaps = coverage_gaps_from_row(row)
    if int(gaps["graph_gap_count"]) > 0 or not bool(row.get("graph_available")):
        limitations.append("graph_partial")
    if int(gaps["content_gap_count"]) > 0 or not bool(
        row.get("server_content_available")
    ):
        limitations.append("content_partial")

    return limitations


def _normalize_coverage_row(row: dict[str, Any]) -> dict[str, Any]:
    """Normalize one persisted runtime coverage row into the public shape."""

    summary = coverage_summary_from_row(row) or {}
    gaps = coverage_gaps_from_row(row)
    return {
        "run_id": row.get("run_id"),
        "repo_id": row.get("repo_id"),
        "repo_name": row.get("repo_name"),
        "repo_path": row.get("repo_path"),
        "status": row.get("status"),
        "phase": row.get("phase"),
        "finalization_status": row.get("finalization_status"),
        "graph_available": bool(row.get("graph_available")),
        "server_content_available": bool(row.get("server_content_available")),
        "discovered_file_count": int(row.get("discovered_file_count") or 0),
        "graph_recursive_file_count": int(row.get("graph_recursive_file_count") or 0),
        "content_file_count": int(row.get("content_file_count") or 0),
        "content_entity_count": int(row.get("content_entity_count") or 0),
        "root_file_count": int(row.get("root_file_count") or 0),
        "root_directory_count": int(row.get("root_directory_count") or 0),
        "top_level_function_count": int(row.get("top_level_function_count") or 0),
        "class_method_count": int(row.get("class_method_count") or 0),
        "total_function_count": int(row.get("total_function_count") or 0),
        "class_count": int(row.get("class_count") or 0),
        "last_error": _normalize_value(row.get("last_error")),
        "created_at": _normalize_value(row.get("created_at")),
        "updated_at": _normalize_value(row.get("updated_at")),
        "commit_finished_at": _normalize_value(row.get("commit_finished_at")),
        "finalization_finished_at": _normalize_value(
            row.get("finalization_finished_at")
        ),
        "limitations": summary.get("limitations", []),
        **gaps,
        "summary": summary,
    }


def get_repository_coverage_payload(
    *, repo_id: str, run_id: str | None = None
) -> dict[str, Any]:
    """Return durable repository coverage for one canonical repository ID."""

    row = get_runtime_repository_coverage(repo_id=repo_id, run_id=run_id)
    if row is None:
        return {"error": f"Repository coverage not found: {repo_id}"}
    return _normalize_coverage_row(row)


def list_repository_coverage_payload(
    *,
    run_id: str | None = None,
    only_incomplete: bool = False,
    statuses: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Return durable repository coverage rows for one run or across runs."""

    rows = list_runtime_repository_coverage(
        run_id=run_id,
        only_incomplete=only_incomplete,
        statuses=statuses,
        limit=limit,
    )
    return {
        "run_id": run_id,
        "repositories": [_normalize_coverage_row(row) for row in rows],
    }
