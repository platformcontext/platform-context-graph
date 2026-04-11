"""Pending backfill request helpers for repo-sync cycles."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from platform_context_graph.facts.state import get_fact_work_queue
from platform_context_graph.facts.work_queue.models import FactBackfillRequestRow
from platform_context_graph.facts.work_queue.recovery import (
    delete_backfill_requests,
    list_backfill_requests,
    list_repository_ids_for_source_run,
)
from platform_context_graph.indexing.coordinator_facts_support import (
    repository_id_for_path,
)


@dataclass(frozen=True, slots=True)
class RepoSyncBackfillSelection:
    """Resolved repo-sync backfill request planning for one cycle."""

    forced_repositories: tuple[Path, ...] = ()
    satisfiable_request_ids: tuple[str, ...] = ()
    unresolved_summaries: tuple[str, ...] = ()


def plan_repo_sync_backfills(
    *,
    discovered_repository_paths: Iterable[Path],
    get_fact_work_queue_fn: Callable[[], object | None] = get_fact_work_queue,
    repository_id_for_path_fn: Callable[[Path], str] = repository_id_for_path,
) -> RepoSyncBackfillSelection:
    """Resolve pending backfill requests onto discovered local checkouts."""

    queue = get_fact_work_queue_fn()
    if queue is None or not getattr(queue, "enabled", True):
        return RepoSyncBackfillSelection()

    requests = list_backfill_requests(queue)
    if not requests:
        return RepoSyncBackfillSelection()

    repository_paths_by_id: dict[str, Path] = {}
    for repo_path in discovered_repository_paths:
        resolved_path = repo_path.resolve()
        try:
            repository_paths_by_id[repository_id_for_path_fn(resolved_path)] = (
                resolved_path
            )
        except Exception:
            continue

    forced_paths: set[Path] = set()
    satisfiable_request_ids: list[str] = []
    source_run_repository_ids_cache: dict[str, set[str]] = {}
    unresolved_summaries: list[str] = []
    for request in requests:
        requested_repository_ids = _request_repository_ids(
            queue=queue,
            request=request,
            source_run_repository_ids_cache=source_run_repository_ids_cache,
        )
        if not requested_repository_ids:
            unresolved_summaries.append(_request_summary(request))
            continue
        missing_repository_ids = sorted(
            repo_id
            for repo_id in requested_repository_ids
            if repo_id not in repository_paths_by_id
        )
        if missing_repository_ids:
            unresolved_summaries.append(
                _request_summary(
                    request,
                    missing_repository_ids=missing_repository_ids,
                )
            )
            continue
        forced_paths.update(
            repository_paths_by_id[repo_id] for repo_id in requested_repository_ids
        )
        satisfiable_request_ids.append(request.backfill_request_id)

    return RepoSyncBackfillSelection(
        forced_repositories=tuple(sorted(forced_paths, key=str)),
        satisfiable_request_ids=tuple(sorted(set(satisfiable_request_ids))),
        unresolved_summaries=tuple(unresolved_summaries),
    )


def satisfy_repo_sync_backfills(
    *,
    backfill_request_ids: list[str],
    get_fact_work_queue_fn: Callable[[], object | None] = get_fact_work_queue,
) -> int:
    """Delete satisfied backfill requests after a successful sync index."""

    queue = get_fact_work_queue_fn()
    if queue is None or not getattr(queue, "enabled", True):
        return 0
    return delete_backfill_requests(
        queue,
        backfill_request_ids=backfill_request_ids,
    )


def _request_repository_ids(
    *,
    queue: object,
    request: FactBackfillRequestRow,
    source_run_repository_ids_cache: dict[str, set[str]] | None = None,
) -> set[str]:
    """Resolve the repository ids targeted by one backfill request."""

    repository_id = str(request.repository_id or "").strip()
    source_run_id = str(request.source_run_id or "").strip()
    if repository_id and source_run_id:
        source_run_repository_ids = _source_run_repository_ids(
            queue=queue,
            source_run_id=source_run_id,
            source_run_repository_ids_cache=source_run_repository_ids_cache,
        )
        return {repository_id} if repository_id in source_run_repository_ids else set()
    if repository_id:
        return {repository_id}
    if source_run_id:
        return _source_run_repository_ids(
            queue=queue,
            source_run_id=source_run_id,
            source_run_repository_ids_cache=source_run_repository_ids_cache,
        )
    return set()


def _source_run_repository_ids(
    *,
    queue: object,
    source_run_id: str,
    source_run_repository_ids_cache: dict[str, set[str]] | None = None,
) -> set[str]:
    """Return cached repository ids for one source run when available."""

    if source_run_repository_ids_cache is None:
        return set(
            list_repository_ids_for_source_run(queue, source_run_id=source_run_id)
        )

    cached_repository_ids = source_run_repository_ids_cache.get(source_run_id)
    if cached_repository_ids is None:
        cached_repository_ids = set(
            list_repository_ids_for_source_run(queue, source_run_id=source_run_id)
        )
        source_run_repository_ids_cache[source_run_id] = cached_repository_ids
    return cached_repository_ids


def _request_summary(
    request: FactBackfillRequestRow,
    *,
    missing_repository_ids: list[str] | None = None,
) -> str:
    """Return one bounded human-readable backfill request summary."""

    selectors: list[str] = []
    if request.repository_id:
        selectors.append(f"repository_id={request.repository_id}")
    if request.source_run_id:
        selectors.append(f"source_run_id={request.source_run_id}")
    if missing_repository_ids:
        missing_preview = ", ".join(missing_repository_ids[:3])
        if len(missing_repository_ids) > 3:
            missing_preview = f"{missing_preview}, ..."
        selectors.append(f"missing={missing_preview}")
    selector_text = " ".join(selectors) or "unscoped"
    return f"{request.backfill_request_id} ({selector_text})"


__all__ = [
    "RepoSyncBackfillSelection",
    "plan_repo_sync_backfills",
    "satisfy_repo_sync_backfills",
]
