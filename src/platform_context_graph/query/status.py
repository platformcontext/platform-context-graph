"""Query helpers for runtime ingester status and control."""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any

from ..observability import get_observability, trace_query
from .repositories.common import get_db_manager, resolve_repository
from .status_projection import (
    checkpoint_status_payload,
    runtime_run_summary_from_status,
)

# Go data plane owns status store, facts queue, and shared projection.
# These imports are optional — the Python API degrades gracefully when absent.
try:
    from ..facts.state import get_fact_work_queue, get_projection_decision_store
    from ..facts.state import get_shared_projection_intent_store
except ImportError:
    get_fact_work_queue = lambda: None  # noqa: E731
    get_projection_decision_store = lambda: None  # noqa: E731
    get_shared_projection_intent_store = lambda: None  # noqa: E731

try:
    from ..runtime.status_store import (
        get_runtime_status_store,
        request_ingester_reindex,
        request_ingester_scan,
    )
except ImportError:
    get_runtime_status_store = lambda: None  # noqa: E731
    request_ingester_reindex = lambda **kw: None  # noqa: E731
    request_ingester_scan = lambda **kw: None  # noqa: E731

try:
    from .status_shared_projection import apply_shared_projection_pending_status
    from .status_shared_projection import enrich_shared_projection_status
except ImportError:
    def apply_shared_projection_pending_status(payload, **kw):  # type: ignore[misc]
        return payload
    def enrich_shared_projection_status(payload, **kw):  # type: ignore[misc]
        return payload

__all__ = [
    "KNOWN_INGESTERS",
    "describe_index_status",
    "default_index_status_target",
    "resolve_index_status_target",
    "get_ingester_status",
    "list_ingesters",
    "request_ingester_reindex_control",
    "request_ingester_scan_control",
]

KNOWN_INGESTERS = ("repository",)
_INGESTER_ALIASES = {
    "repository": ("repository", "bootstrap-index", "repo-sync", "workspace-index"),
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
        "shared_projection_pending_repositories": 0,
        "shared_projection_backlog": [],
        "shared_projection_tuning": None,
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


def _describe_index_run(target: str | Path) -> dict[str, Any] | None:
    """Lazily import the coordinator status helper to avoid circular imports."""

    from ..indexing.run_status import describe_index_run

    return describe_index_run(target)


def _checkpoint_status_fallback(ingester: str) -> dict[str, Any] | None:
    """Return checkpoint-derived ingester status when runtime persistence lags."""

    target = _checkpoint_target_for_ingester(ingester)
    if target is None:
        return None
    summary = _describe_index_run(target)
    if summary is None:
        return None
    return checkpoint_status_payload(
        ingester=ingester,
        source_mode=os.getenv("PCG_REPO_SOURCE_MODE"),
        summary=summary,
    )


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
        return checkpoint_updated_at is not None and (
            runtime_updated_at is None or checkpoint_updated_at >= runtime_updated_at
        )
    if checkpoint_updated_at is None or runtime_updated_at is None:
        return False
    return checkpoint_updated_at > runtime_updated_at


def _runtime_run_summary_fallback(
    _database: Any,
    *,
    requested_target: str | Path | None,
    resolved_target: str | Path | None,
    ingester: str,
) -> dict[str, Any] | None:
    """Return an active run summary synthesized from shared runtime status."""

    status_payload = get_ingester_status(_database, ingester=ingester)
    summary = runtime_run_summary_from_status(
        status_payload,
        fallback_root_path=default_index_status_target(ingester),
    )
    if summary is None:
        return None

    if isinstance(resolved_target, Path):
        root_path = summary.get("root_path")
        if not isinstance(root_path, str) or not root_path.strip():
            return None
        if Path(root_path).resolve() != resolved_target.resolve():
            return None
        return summary

    if isinstance(requested_target, Path):
        return None

    candidate = str(requested_target).strip() if requested_target is not None else ""
    if candidate and summary.get("run_id") != candidate:
        return None
    return summary


def describe_index_status(
    _database: Any,
    *,
    target: str | Path | None,
    ingester: str = "repository",
) -> dict[str, Any] | None:
    """Return the latest run summary for one target in local or deployed mode."""

    resolved_target = resolve_index_status_target(
        _database,
        target=target,
        ingester=ingester,
    )
    if resolved_target is not None:
        summary = _describe_index_run(resolved_target)
        if summary is not None:
            return summary
    return _runtime_run_summary_fallback(
        _database,
        requested_target=target,
        resolved_target=resolved_target,
        ingester=ingester,
    )


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
        queue = get_fact_work_queue()
        shared_projection_intent_store = get_shared_projection_intent_store()
        decision_store = get_projection_decision_store()
        if store is not None and store.enabled:
            result = _select_runtime_status_payload(store, ingester=ingester)
            if result is not None:
                if (
                    checkpoint_fallback is not None
                    and _runtime_status_should_yield_to_checkpoint(
                        result, checkpoint_fallback
                    )
                ):
                    result = checkpoint_fallback
                return enrich_shared_projection_status(
                    result,
                    queue=queue,
                    shared_projection_intent_store=shared_projection_intent_store,
                    decision_store=decision_store,
                )
        if checkpoint_fallback is not None:
            return enrich_shared_projection_status(
                checkpoint_fallback,
                queue=queue,
                shared_projection_intent_store=shared_projection_intent_store,
                decision_store=decision_store,
            )
        return apply_shared_projection_pending_status(
            _default_status(ingester),
            pending_count=0,
            backlog=[],
            queue=queue,
            decision_store=decision_store,
        )


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
