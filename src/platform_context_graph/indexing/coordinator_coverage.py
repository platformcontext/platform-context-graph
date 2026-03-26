"""Durable repository coverage publishing helpers for checkpointed runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ..observability import get_observability
from ..content.state import get_postgres_content_provider
from ..query.repositories.graph_counts import repository_graph_counts
from ..repository_identity import git_remote_for_path, repository_metadata
from ..runtime.status_store import get_repository_coverage, upsert_repository_coverage
from ..utils.debug_log import emit_log_call, info_logger, warning_logger

__all__ = [
    "publish_repository_coverage",
    "publish_run_repository_coverage",
]


_GRAPH_COUNT_FIELD_MAP = {
    "root_file_count": "root_file_count",
    "root_directory_count": "root_directory_count",
    "file_count": "graph_recursive_file_count",
    "top_level_function_count": "top_level_function_count",
    "class_method_count": "class_method_count",
    "total_function_count": "total_function_count",
    "class_count": "class_count",
}
_CONTENT_COUNT_FIELDS = ("content_file_count", "content_entity_count")


def _coverage_metadata(repo_path: Path) -> dict[str, Any]:
    """Build normalized repository identity metadata for one repo path."""

    resolved = repo_path.resolve()
    return repository_metadata(
        name=resolved.name,
        local_path=str(resolved),
        remote_url=git_remote_for_path(resolved),
    )


def _graph_counts(builder: Any, metadata: dict[str, Any]) -> dict[str, int]:
    """Return graph-derived counts for one indexed repository."""

    with builder.db_manager.get_driver().session() as session:
        return repository_graph_counts(
            session,
            {
                "id": metadata["id"],
                "path": metadata["local_path"],
                "local_path": metadata["local_path"],
            },
        )


def _content_counts(builder: Any, repo_id: str) -> dict[str, int]:
    """Return PostgreSQL-backed content counts for one repository."""

    content_provider = getattr(builder, "_content_provider", None)
    if content_provider is None:
        content_provider = get_postgres_content_provider()
        builder._content_provider = content_provider
    if content_provider is None or not getattr(content_provider, "enabled", False):
        return {
            "content_file_count": 0,
            "content_entity_count": 0,
        }
    if not hasattr(content_provider, "get_repository_content_counts"):
        return {
            "content_file_count": 0,
            "content_entity_count": 0,
        }
    return content_provider.get_repository_content_counts(repo_id=repo_id)


def _existing_coverage_counts(run_id: str, repo_id: str) -> dict[str, int]:
    """Return the latest persisted coverage counters for one run/repository."""

    row = get_repository_coverage(repo_id=repo_id, run_id=run_id) or {}
    counts: dict[str, int] = {}
    for field, row_key in _GRAPH_COUNT_FIELD_MAP.items():
        counts[field] = int(row.get(row_key) or 0)
    for field in _CONTENT_COUNT_FIELDS:
        counts[field] = int(row.get(field) or 0)
    return counts


def publish_repository_coverage(
    *,
    builder: Any,
    run_state: Any,
    repo_state: Any,
    repo_path: Path,
    include_graph_counts: bool,
    include_content_counts: bool,
) -> None:
    """Persist one repository coverage row for the current checkpoint state."""

    metadata = _coverage_metadata(repo_path)
    observability = get_observability()
    existing_counts = (
        _existing_coverage_counts(run_state.run_id, metadata["id"])
        if not include_graph_counts or not include_content_counts
        else {}
    )
    graph_counts = {
        "root_file_count": existing_counts.get("root_file_count", 0),
        "root_directory_count": existing_counts.get("root_directory_count", 0),
        "file_count": existing_counts.get("file_count", 0),
        "top_level_function_count": existing_counts.get(
            "top_level_function_count", 0
        ),
        "class_method_count": existing_counts.get("class_method_count", 0),
        "total_function_count": existing_counts.get("total_function_count", 0),
        "class_count": existing_counts.get("class_count", 0),
    }
    if include_graph_counts:
        graph_counts = _graph_counts(builder, metadata)

    content_counts = {
        "content_file_count": existing_counts.get("content_file_count", 0),
        "content_entity_count": existing_counts.get("content_entity_count", 0),
    }
    if include_content_counts:
        content_counts = _content_counts(builder, metadata["id"])
    graph_gap_count = max(int(repo_state.file_count or 0) - graph_counts["file_count"], 0)
    content_gap_count = max(
        graph_counts["file_count"] - content_counts["content_file_count"],
        0,
    )
    with observability.start_span(
        "pcg.indexing.publish_repository_coverage",
        component=observability.component,
        attributes={
            "pcg.run_id": run_state.run_id,
            "pcg.repo_id": metadata["id"],
            "pcg.repo_name": metadata["name"],
            "pcg.coverage.discovered_file_count": int(repo_state.file_count or 0),
            "pcg.coverage.graph_recursive_file_count": graph_counts["file_count"],
            "pcg.coverage.content_file_count": content_counts["content_file_count"],
            "pcg.coverage.graph_gap_count": graph_gap_count,
            "pcg.coverage.content_gap_count": content_gap_count,
        },
    ):
        upsert_repository_coverage(
            run_id=run_state.run_id,
            repo_id=metadata["id"],
            repo_name=metadata["name"],
            repo_path=metadata["local_path"],
            status=repo_state.status,
            phase=repo_state.phase,
            finalization_status=run_state.finalization_status,
            discovered_file_count=repo_state.file_count,
            graph_recursive_file_count=graph_counts["file_count"],
            content_file_count=content_counts["content_file_count"],
            content_entity_count=content_counts["content_entity_count"],
            root_file_count=graph_counts["root_file_count"],
            root_directory_count=graph_counts["root_directory_count"],
            top_level_function_count=graph_counts["top_level_function_count"],
            class_method_count=graph_counts["class_method_count"],
            total_function_count=graph_counts["total_function_count"],
            class_count=graph_counts["class_count"],
            graph_available=(
                graph_counts["file_count"] > 0
                or graph_counts["root_file_count"] > 0
                or graph_counts["root_directory_count"] > 0
            ),
            server_content_available=(
                content_counts["content_file_count"] > 0
                or content_counts["content_entity_count"] > 0
            ),
            last_error=repo_state.error or run_state.last_error,
            created_at=run_state.created_at,
            updated_at=run_state.updated_at,
            commit_finished_at=repo_state.commit_finished_at,
            finalization_finished_at=run_state.finalization_finished_at,
        )
        emit_log_call(
            info_logger,
            "Published durable repository coverage",
            event_name="indexing.repository_coverage.published",
            extra_keys={
                "run_id": run_state.run_id,
                "repo_id": metadata["id"],
                "repo_name": metadata["name"],
                "discovered_file_count": int(repo_state.file_count or 0),
                "graph_recursive_file_count": graph_counts["file_count"],
                "content_file_count": content_counts["content_file_count"],
                "content_entity_count": content_counts["content_entity_count"],
                "graph_gap_count": graph_gap_count,
                "content_gap_count": content_gap_count,
                "phase": repo_state.phase,
                "status": repo_state.status,
                "finalization_status": run_state.finalization_status,
            },
        )


def publish_run_repository_coverage(
    *,
    builder: Any,
    run_state: Any,
    repo_paths: list[Path],
    include_graph_counts: bool,
    include_content_counts: bool,
) -> None:
    """Persist coverage rows for every repository in the current run."""

    for repo_path in repo_paths:
        repo_state = run_state.repositories[str(repo_path.resolve())]
        try:
            publish_repository_coverage(
                builder=builder,
                run_state=run_state,
                repo_state=repo_state,
                repo_path=repo_path,
                include_graph_counts=include_graph_counts,
                include_content_counts=include_content_counts,
            )
        except Exception as exc:
            warning_logger(
                "Skipping repository coverage publish for "
                f"{repo_path.resolve()}: {exc}"
            )
