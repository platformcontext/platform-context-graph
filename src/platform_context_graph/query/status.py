"""Query helpers for runtime ingester status and control."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..observability import get_observability, trace_query
from ..runtime.status_store import (
    get_runtime_status_store,
    request_ingester_reindex,
    request_ingester_scan,
)
from .repositories.common import get_db_manager, resolve_repository

__all__ = [
    "KNOWN_INGESTERS",
    "default_index_status_target",
    "resolve_index_status_target",
    "get_ingester_status",
    "list_ingesters",
    "request_ingester_reindex_control",
    "request_ingester_scan_control",
]

KNOWN_INGESTERS = ("repository",)
_INGESTER_ALIASES = {
    "repository": ("repository", "bootstrap-index", "repo-sync"),
}
_TIMESTAMP_FIELDS = (
    "last_attempt_at",
    "last_success_at",
    "next_retry_at",
    "active_phase_started_at",
    "active_last_progress_at",
    "active_commit_started_at",
    "scan_requested_at",
    "scan_started_at",
    "scan_completed_at",
    "updated_at",
)


def _default_status(ingester: str) -> dict[str, Any]:
    """Return the default ingester status payload when no row exists yet."""

    return {
        "runtime_family": "ingester",
        "ingester": ingester,
        "provider": ingester,
        "source_mode": os.getenv("PCG_REPO_SOURCE_MODE"),
        "status": "bootstrap_pending",
        "finalization_status": None,
        "active_run_id": None,
        "last_attempt_at": None,
        "last_success_at": None,
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": None,
        "active_repository_path": None,
        "active_phase": None,
        "active_phase_started_at": None,
        "active_current_file": None,
        "active_last_progress_at": None,
        "active_commit_started_at": None,
        "repository_count": 0,
        "pulled_repositories": 0,
        "in_sync_repositories": 0,
        "pending_repositories": 0,
        "completed_repositories": 0,
        "failed_repositories": 0,
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": None,
    }


def _normalize_status_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Convert status-store timestamps to stable ISO-8601 strings."""

    normalized = dict(payload)
    for field in _TIMESTAMP_FIELDS:
        value = normalized.get(field)
        if isinstance(value, datetime):
            normalized[field] = value.isoformat()
    return normalized


def _status_aliases(ingester: str) -> tuple[str, ...]:
    """Return provider aliases that feed one public ingester contract."""

    return _INGESTER_ALIASES.get(ingester, (ingester,))


def _select_runtime_status_payload(
    store: Any,
    *,
    ingester: str,
) -> dict[str, Any] | None:
    """Return the freshest runtime-status row for one public ingester."""

    candidates: list[dict[str, Any]] = []
    for alias in _status_aliases(ingester):
        result = store.get_runtime_status(ingester=alias)
        if result is None:
            continue
        normalized = _normalize_status_payload(result)
        normalized["ingester"] = ingester
        normalized["provider"] = str(result.get("provider") or alias)
        candidates.append(normalized)

    if not candidates:
        return None

    def _sort_key(payload: dict[str, Any]) -> tuple[int, str, str]:
        status = str(payload.get("status") or "")
        timestamp = str(
            payload.get("active_last_progress_at")
            or payload.get("updated_at")
            or payload.get("last_attempt_at")
            or ""
        )
        return (
            0 if status == "bootstrap_pending" else 1,
            timestamp,
            str(payload.get("provider") or ""),
        )

    return max(candidates, key=_sort_key)


def _checkpoint_target_for_ingester(ingester: str) -> Path | None:
    """Return the configured checkpoint root used by one ingester."""

    if ingester != "repository":
        return None

    # Checkpointed runs are keyed by the working checkout root, not the source
    # discovery root. In filesystem mode that is still ``PCG_REPOS_DIR``.
    target = os.getenv("PCG_REPOS_DIR") or os.getenv("PCG_FILESYSTEM_ROOT")

    if target is None or not target.strip():
        return None
    return Path(target).resolve()


def default_index_status_target(ingester: str = "repository") -> Path | None:
    """Return the default checkpoint target used by index-status surfaces."""

    return _checkpoint_target_for_ingester(ingester)


def resolve_index_status_target(
    database: Any,
    *,
    target: str | Path | None,
    ingester: str = "repository",
) -> str | Path | None:
    """Resolve a repo name, path, or run ID for index-status lookups."""

    if isinstance(target, Path):
        return target

    if target is None:
        return default_index_status_target(ingester)

    candidate = str(target).strip()
    if not candidate:
        return default_index_status_target(ingester)

    if all(char in "0123456789abcdef" for char in candidate.lower()):
        return candidate

    expanded = Path(candidate).expanduser()
    if expanded.is_absolute():
        return expanded.resolve()

    db_manager = get_db_manager(database)
    if callable(getattr(db_manager, "get_driver", None)):
        with db_manager.get_driver().session() as session:
            repo = resolve_repository(session, candidate)
        if repo is not None:
            local_path = repo.get("local_path") or repo.get("path")
            if isinstance(local_path, str) and local_path.strip():
                return Path(local_path).resolve()

    return candidate


def _active_repository_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return the best active repository from one checkpoint summary."""

    repositories = summary.get("repositories")
    if not isinstance(repositories, list):
        return None

    active_states = {"running", "parsed", "commit_incomplete"}
    active_repos = [
        repo
        for repo in repositories
        if isinstance(repo, dict) and repo.get("status") in active_states
    ]
    if not active_repos:
        return None

    def _sort_key(repo: dict[str, Any]) -> tuple[str, str]:
        return (
            str(repo.get("last_progress_at") or repo.get("updated_at") or ""),
            str(repo.get("repo_path") or ""),
        )

    return max(active_repos, key=_sort_key)


def _active_finalization_from_summary(summary: dict[str, Any]) -> dict[str, Any] | None:
    """Return active finalization details when no repository is actively running."""

    if summary.get("finalization_status") != "running":
        return None
    stage_name = summary.get("finalization_current_stage")
    stage_details = summary.get("finalization_stage_details")
    current_file = None
    if isinstance(stage_details, dict) and isinstance(stage_name, str):
        current_stage_details = stage_details.get(stage_name)
        if isinstance(current_stage_details, dict):
            current_file = current_stage_details.get("current_file")
    return {
        "active_phase": (
            f"finalizing:{stage_name}" if isinstance(stage_name, str) else "finalizing"
        ),
        "active_phase_started_at": (
            summary.get("finalization_stage_started_at")
            or summary.get("finalization_started_at")
        ),
        "active_current_file": current_file,
        "active_last_progress_at": summary.get("updated_at"),
    }


def _derive_finalization_status(
    summary: dict[str, Any], public_status: str
) -> str | None:
    """Derive the finalization status from run state or active phase signals."""

    explicit = summary.get("finalization_status")
    if isinstance(explicit, str) and explicit:
        return explicit
    active_phase = str(summary.get("active_phase") or "")
    if active_phase.startswith("finalizing:") or active_phase == "finalizing":
        return "running"
    if public_status == "completed":
        return "completed"
    return None


def _checkpoint_status_payload(
    *, ingester: str, summary: dict[str, Any]
) -> dict[str, Any]:
    """Project checkpointed run state into the ingester-status response shape."""

    active_repo = _active_repository_from_summary(summary)
    active_finalization = (
        _active_finalization_from_summary(summary)
        if active_repo is None
        else None
    )
    run_status = str(summary.get("status") or "bootstrap_pending")
    public_status = "indexing" if run_status == "running" else run_status
    updated_at = summary.get("updated_at")
    finalization_status = _derive_finalization_status(summary, public_status)
    return {
        "runtime_family": "ingester",
        "ingester": ingester,
        "provider": ingester,
        "source_mode": os.getenv("PCG_REPO_SOURCE_MODE"),
        "status": public_status,
        "finalization_status": finalization_status,
        "active_run_id": summary.get("run_id"),
        "last_attempt_at": summary.get("created_at"),
        "last_success_at": updated_at if public_status == "completed" else None,
        "next_retry_at": None,
        "last_error_kind": None,
        "last_error_message": summary.get("last_error"),
        "active_repository_path": (
            active_repo.get("repo_path") if active_repo is not None else None
        ),
        "active_phase": (
            active_repo.get("phase")
            if active_repo is not None
            else (
                active_finalization.get("active_phase")
                if active_finalization is not None
                else None
            )
        ),
        "active_phase_started_at": (
            active_repo.get("phase_started_at")
            if active_repo is not None
            else (
                active_finalization.get("active_phase_started_at")
                if active_finalization is not None
                else None
            )
        ),
        "active_current_file": (
            active_repo.get("current_file")
            if active_repo is not None
            else (
                active_finalization.get("active_current_file")
                if active_finalization is not None
                else None
            )
        ),
        "active_last_progress_at": (
            active_repo.get("last_progress_at")
            if active_repo is not None
            else (
                active_finalization.get("active_last_progress_at")
                if active_finalization is not None
                else None
            )
        ),
        "active_commit_started_at": (
            active_repo.get("commit_started_at") if active_repo is not None else None
        ),
        "repository_count": int(summary.get("repository_count") or 0),
        "pulled_repositories": int(summary.get("repository_count") or 0),
        "in_sync_repositories": int(summary.get("completed_repositories") or 0),
        "pending_repositories": int(summary.get("pending_repositories") or 0),
        "completed_repositories": int(summary.get("completed_repositories") or 0),
        "failed_repositories": int(summary.get("failed_repositories") or 0),
        "scan_request_state": "idle",
        "scan_request_token": None,
        "scan_requested_at": None,
        "scan_requested_by": None,
        "scan_started_at": None,
        "scan_completed_at": None,
        "scan_error_message": None,
        "updated_at": updated_at,
    }


def _describe_index_run(target: Path) -> dict[str, Any] | None:
    """Lazily import the coordinator status helper to avoid circular imports."""

    from ..indexing.coordinator import describe_index_run

    return describe_index_run(target)


def _checkpoint_status_fallback(ingester: str) -> dict[str, Any] | None:
    """Return checkpoint-derived ingester status when runtime persistence lags."""

    target = _checkpoint_target_for_ingester(ingester)
    if target is None:
        return None
    summary = _describe_index_run(target)
    if summary is None:
        return None
    return _checkpoint_status_payload(ingester=ingester, summary=summary)


def _parse_status_timestamp(value: Any) -> datetime | None:
    """Parse a status timestamp value into a comparable datetime."""

    if isinstance(value, datetime):
        return value
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate:
        return None
    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


def _status_updated_at(payload: dict[str, Any]) -> datetime | None:
    """Return the freshest comparable timestamp from one status payload."""

    for field in ("active_last_progress_at", "updated_at", "last_attempt_at"):
        parsed = _parse_status_timestamp(payload.get(field))
        if parsed is not None:
            return parsed
    return None


def _runtime_status_should_yield_to_checkpoint(
    runtime_payload: dict[str, Any],
    checkpoint_payload: dict[str, Any],
) -> bool:
    """Report whether checkpoint status should replace the persisted runtime row."""

    runtime_status = str(runtime_payload.get("status") or "")
    if runtime_status == "bootstrap_pending":
        return True

    checkpoint_status = str(checkpoint_payload.get("status") or "")
    runtime_updated_at = _status_updated_at(runtime_payload)
    checkpoint_updated_at = _status_updated_at(checkpoint_payload)
    if checkpoint_status != "indexing":
        return False
    if runtime_status != "indexing":
        return (
            checkpoint_updated_at is not None
            and (
                runtime_updated_at is None
                or checkpoint_updated_at >= runtime_updated_at
            )
        )
    if checkpoint_updated_at is None or runtime_updated_at is None:
        return False
    return checkpoint_updated_at > runtime_updated_at


def list_ingesters(_database: Any) -> list[dict[str, Any]]:
    """Return the current status for each known ingester."""

    with trace_query("runtime_list_ingesters"):
        return [
            get_ingester_status(_database, ingester=name) for name in KNOWN_INGESTERS
        ]


def get_ingester_status(
    _database: Any,
    *,
    ingester: str = "repository",
) -> dict[str, Any]:
    """Return persisted runtime status for one ingester."""

    with trace_query("runtime_ingester_status"):
        store = get_runtime_status_store()
        checkpoint_fallback = _checkpoint_status_fallback(ingester)
        if store is not None and store.enabled:
            result = _select_runtime_status_payload(store, ingester=ingester)
            if result is not None:
                if checkpoint_fallback is not None and _runtime_status_should_yield_to_checkpoint(
                    result, checkpoint_fallback
                ):
                    return checkpoint_fallback
                return result
        if checkpoint_fallback is not None:
            return checkpoint_fallback
        return _default_status(ingester)


def request_ingester_scan_control(
    _database: Any,
    *,
    ingester: str = "repository",
    requested_by: str = "api",
) -> dict[str, Any]:
    """Persist a manual ingester scan request and return its accepted state."""

    with trace_query("runtime_request_ingester_scan"):
        result = request_ingester_scan(ingester=ingester, requested_by=requested_by)
        telemetry = get_observability()
        if result is None:
            telemetry.record_ingester_scan_request(
                ingester=ingester,
                phase="requested",
                requested_by=requested_by,
                accepted=False,
            )
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": ingester,
                "accepted": False,
                "scan_request_token": "",
                "scan_request_state": "unavailable",
                "scan_requested_at": None,
                "scan_requested_by": requested_by,
            }
        telemetry.record_ingester_scan_request(
            ingester=ingester,
            phase="requested",
            requested_by=requested_by,
            accepted=True,
        )
        return _normalize_status_payload(
            {
                "runtime_family": "ingester",
                "ingester": result["ingester"],
                "provider": result["ingester"],
                "accepted": True,
                "scan_request_token": result["scan_request_token"],
                "scan_request_state": result["scan_request_state"],
                "scan_requested_at": result["scan_requested_at"],
                "scan_requested_by": result.get("scan_requested_by"),
            }
        )


def request_ingester_reindex_control(
    _database: Any,
    *,
    ingester: str = "repository",
    requested_by: str = "api",
    force: bool = True,
    scope: str = "workspace",
) -> dict[str, Any]:
    """Persist a manual ingester reindex request and return its accepted state."""

    with trace_query("runtime_request_ingester_reindex"):
        result = request_ingester_reindex(
            ingester=ingester,
            requested_by=requested_by,
            force=force,
            scope=scope,
        )
        if result is None:
            return {
                "runtime_family": "ingester",
                "ingester": ingester,
                "provider": ingester,
                "accepted": False,
                "reindex_request_token": "",
                "reindex_request_state": "unavailable",
                "reindex_requested_at": None,
                "reindex_requested_by": requested_by,
                "requested_force": force,
                "requested_scope": scope,
                "run_id": None,
            }
        return _normalize_status_payload(
            {
                "runtime_family": "ingester",
                "ingester": result["ingester"],
                "provider": result["ingester"],
                "accepted": True,
                "reindex_request_token": result["reindex_request_token"],
                "reindex_request_state": result["reindex_request_state"],
                "reindex_requested_at": result["reindex_requested_at"],
                "reindex_requested_by": result.get("reindex_requested_by"),
                "requested_force": bool(result.get("requested_force", True)),
                "requested_scope": result.get("requested_scope") or scope,
                "run_id": result.get("run_id"),
            }
        )
