#!/usr/bin/env python3
"""Support code for the repository coverage backfill CLI."""

from __future__ import annotations

import os
from dataclasses import asdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from platform_context_graph.query.repositories.graph_counts import repository_graph_counts
from platform_context_graph.repository_identity import git_remote_for_path, repository_metadata
from platform_context_graph.runtime.status_store import (
    get_repository_coverage as get_runtime_repository_coverage,
    upsert_repository_coverage,
)

__all__ = [
    "CoverageBackfillResult",
    "CoverageUpdate",
    "RuntimeCoverageBackfillStore",
    "default_run_root",
    "load_target_run_state",
    "run_backfill",
]


@dataclass(frozen=True, slots=True)
class CoverageUpdate:
    """One durable repository coverage update."""

    run_id: str
    repo_id: str
    repo_name: str
    repo_path: str
    status: str
    phase: str | None
    finalization_status: str | None
    discovered_file_count: int
    graph_recursive_file_count: int
    content_file_count: int
    content_entity_count: int
    root_file_count: int
    root_directory_count: int
    top_level_function_count: int
    class_method_count: int
    total_function_count: int
    class_count: int
    graph_available: bool
    server_content_available: bool
    last_error: str | None
    created_at: str | None
    updated_at: str | None
    commit_finished_at: str | None
    finalization_finished_at: str | None


@dataclass(frozen=True, slots=True)
class CoverageBackfillResult:
    """Summary counters returned by one repository coverage backfill run."""

    run_id: str
    scanned_repositories: int
    updated_repositories: int


class RepositoryCoverageBackfillStore(Protocol):
    """Storage contract used by the repository coverage backfill runner."""

    def graph_counts(self, *, repo_metadata: dict[str, Any]) -> dict[str, int]:
        """Return graph-derived repository counts."""

    def content_counts(self, *, repo_id: str) -> dict[str, int]:
        """Return content-store repository counts."""

    def existing_coverage(
        self, *, run_id: str, repo_id: str
    ) -> dict[str, Any] | None:
        """Return any existing durable coverage row for one repo/run pair."""

    def upsert_repository_coverage(self, update: CoverageUpdate) -> None:
        """Persist one repository coverage row."""


class RuntimeCoverageBackfillStore:
    """Neo4j/Postgres-backed store used by the repository coverage backfill."""

    def __init__(self, *, db_manager: Any, content_provider: Any | None) -> None:
        """Bind the backfill store to graph and content backends."""

        self._db_manager = db_manager
        self._content_provider = content_provider

    def graph_counts(self, *, repo_metadata: dict[str, Any]) -> dict[str, int]:
        """Return graph-derived counts for one repository."""

        with self._db_manager.get_driver().session() as session:
            return repository_graph_counts(
                session,
                {
                    "id": repo_metadata["id"],
                    "path": repo_metadata["local_path"],
                    "local_path": repo_metadata["local_path"],
                },
            )

    def content_counts(self, *, repo_id: str) -> dict[str, int]:
        """Return content-store file/entity counts for one repository."""

        if self._content_provider is None or not getattr(
            self._content_provider, "enabled", False
        ):
            return {"content_file_count": 0, "content_entity_count": 0}
        return self._content_provider.get_repository_content_counts(repo_id=repo_id)

    def existing_coverage(
        self, *, run_id: str, repo_id: str
    ) -> dict[str, Any] | None:
        """Return any existing coverage row for one run/repo pair."""

        return get_runtime_repository_coverage(repo_id=repo_id, run_id=run_id)

    def upsert_repository_coverage(self, update: CoverageUpdate) -> None:
        """Persist one repository coverage row into the runtime store."""

        upsert_repository_coverage(**asdict(update))


def default_run_root() -> Path | None:
    """Return the default checkpoint root inferred from the current environment."""

    root = os.getenv("PCG_REPOS_DIR") or os.getenv("PCG_FILESYSTEM_ROOT")
    if root is None or not root.strip():
        return None
    return Path(root).resolve()


def load_target_run_state(
    *,
    run_id: str | None,
    root_path: Path | None,
    load_run_state_by_id_fn: Any,
    matching_run_states_fn: Any,
) -> Any | None:
    """Return the requested checkpointed run state or the latest run for a root."""

    if run_id is not None:
        return load_run_state_by_id_fn(run_id)

    target_root = root_path or default_run_root()
    if target_root is None:
        return None
    matches = matching_run_states_fn(target_root)
    if not matches:
        return None
    return matches[0]


def run_backfill(
    *,
    store: RepositoryCoverageBackfillStore,
    run_state: Any,
    repo_ids: list[str] | None,
    limit: int | None,
    dry_run: bool,
) -> CoverageBackfillResult:
    """Populate durable repository coverage rows from one checkpointed run."""

    scanned_repositories = 0
    updated_repositories = 0

    for repo_state in sorted(
        run_state.repositories.values(),
        key=lambda item: item.repo_path,
    ):
        repo_path = Path(repo_state.repo_path).resolve()
        metadata = repository_metadata(
            name=repo_path.name,
            local_path=str(repo_path),
            remote_url=git_remote_for_path(repo_path),
        )
        if repo_ids and metadata["id"] not in repo_ids:
            continue
        if limit is not None and scanned_repositories >= limit:
            break

        scanned_repositories += 1
        update = _build_coverage_update(
            store=store,
            run_state=run_state,
            repo_state=repo_state,
            metadata=metadata,
        )
        if dry_run:
            continue
        if _upsert_if_changed(store=store, update=update):
            updated_repositories += 1

    return CoverageBackfillResult(
        run_id=run_state.run_id,
        scanned_repositories=scanned_repositories,
        updated_repositories=updated_repositories,
    )


def _build_coverage_update(
    *,
    store: RepositoryCoverageBackfillStore,
    run_state: Any,
    repo_state: Any,
    metadata: dict[str, Any],
) -> CoverageUpdate:
    """Build one durable repository coverage update from live graph/content truth."""

    graph_counts = store.graph_counts(repo_metadata=metadata)
    content_counts = store.content_counts(repo_id=metadata["id"])
    graph_recursive_file_count = int(graph_counts.get("file_count") or 0)
    root_file_count = int(graph_counts.get("root_file_count") or 0)
    root_directory_count = int(graph_counts.get("root_directory_count") or 0)
    content_file_count = int(content_counts.get("content_file_count") or 0)
    content_entity_count = int(content_counts.get("content_entity_count") or 0)

    return CoverageUpdate(
        run_id=run_state.run_id,
        repo_id=metadata["id"],
        repo_name=metadata["name"],
        repo_path=metadata["local_path"],
        status=repo_state.status,
        phase=repo_state.phase,
        finalization_status=run_state.finalization_status,
        discovered_file_count=int(repo_state.file_count or 0),
        graph_recursive_file_count=graph_recursive_file_count,
        content_file_count=content_file_count,
        content_entity_count=content_entity_count,
        root_file_count=root_file_count,
        root_directory_count=root_directory_count,
        top_level_function_count=int(graph_counts.get("top_level_function_count") or 0),
        class_method_count=int(graph_counts.get("class_method_count") or 0),
        total_function_count=int(graph_counts.get("total_function_count") or 0),
        class_count=int(graph_counts.get("class_count") or 0),
        graph_available=(
            graph_recursive_file_count > 0
            or root_file_count > 0
            or root_directory_count > 0
        ),
        server_content_available=(
            content_file_count > 0 or content_entity_count > 0
        ),
        last_error=repo_state.error or run_state.last_error,
        created_at=run_state.created_at,
        updated_at=repo_state.updated_at or run_state.updated_at,
        commit_finished_at=repo_state.commit_finished_at,
        finalization_finished_at=run_state.finalization_finished_at,
    )


def _upsert_if_changed(
    *,
    store: RepositoryCoverageBackfillStore,
    update: CoverageUpdate,
) -> bool:
    """Persist one coverage row only when it differs from the current stored row."""

    update_payload = asdict(update)
    existing = store.existing_coverage(run_id=update.run_id, repo_id=update.repo_id)
    if existing is not None and _normalized_existing(existing, update_payload) == update_payload:
        return False
    store.upsert_repository_coverage(update)
    return True


def _normalized_existing(
    existing: dict[str, Any], update_payload: dict[str, Any]
) -> dict[str, Any]:
    """Project one stored row into the comparable update payload shape."""

    normalized: dict[str, Any] = {}
    for key in update_payload:
        value = existing.get(key)
        if isinstance(value, datetime):
            normalized[key] = value.isoformat()
        else:
            normalized[key] = value
    return normalized
