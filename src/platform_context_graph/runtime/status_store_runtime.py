"""Singleton and facade helpers for the runtime status store."""

from __future__ import annotations

import os
import threading
from typing import Any

from .status_store_db import PostgresRuntimeStatusStore

_STORE_LOCK = threading.Lock()
_STORE: PostgresRuntimeStatusStore | None = None
_COUNT_FIELDS = frozenset(
    {
        "repository_count",
        "pulled_repositories",
        "in_sync_repositories",
        "pending_repositories",
        "completed_repositories",
        "failed_repositories",
    }
)
_COVERAGE_COUNT_FIELDS = frozenset(
    {
        "discovered_file_count",
        "graph_recursive_file_count",
        "content_file_count",
        "content_entity_count",
        "root_file_count",
        "root_directory_count",
        "top_level_function_count",
        "class_method_count",
        "total_function_count",
        "class_count",
    }
)


def _content_store_enabled() -> bool:
    """Return whether PostgreSQL-backed runtime status should be attempted."""

    raw = os.getenv("PCG_CONTENT_STORE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _dsn() -> str | None:
    """Return the configured PostgreSQL DSN, if any."""

    for key in ("PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def runtime_status_persistence_active() -> bool:
    """Return whether runtime status persistence is currently active."""

    dsn = _dsn()
    return bool(_content_store_enabled() and dsn and PostgresRuntimeStatusStore(dsn).enabled)


def _normalize_count(value: int | None) -> int:
    """Normalize nullable repository count fields before persistence."""

    return 0 if value is None else int(value)


def get_runtime_status_store() -> PostgresRuntimeStatusStore | None:
    """Return the shared runtime status store when configured."""

    global _STORE
    if not _content_store_enabled():
        return None
    dsn = _dsn()
    if not dsn:
        return None
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = PostgresRuntimeStatusStore(dsn)
        return _STORE


def update_runtime_ingester_status(**kwargs: Any) -> None:
    """Persist ingester status when the runtime status store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    for key in _COUNT_FIELDS:
        if key in kwargs:
            kwargs[key] = _normalize_count(kwargs[key])
    store.upsert_runtime_status(**kwargs)


def request_ingester_scan(
    *, ingester: str, requested_by: str = "api"
) -> dict[str, Any] | None:
    """Persist a manual ingester scan request when the status store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return None
    return store.request_scan(ingester=ingester, requested_by=requested_by)


def upsert_repository_coverage(**kwargs: Any) -> None:
    """Persist one durable repository coverage row when configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    for key in _COVERAGE_COUNT_FIELDS:
        if key in kwargs:
            kwargs[key] = _normalize_count(kwargs[key])
    store.upsert_repository_coverage(**kwargs)


def update_latest_repository_coverage_finalization(**kwargs: Any) -> None:
    """Repair finalization-only fields on the latest coverage row per repo."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    store.update_latest_repository_coverage_finalization(**kwargs)


def get_repository_coverage(
    *, repo_id: str, run_id: str | None = None
) -> dict[str, Any] | None:
    """Return one repository coverage row when the runtime store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return None
    return store.get_repository_coverage(repo_id=repo_id, run_id=run_id)


def list_repository_coverage(
    *,
    run_id: str | None = None,
    only_incomplete: bool = False,
    statuses: list[str] | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Return durable repository coverage rows when the runtime store is configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return []
    return store.list_repository_coverage(
        run_id=run_id,
        only_incomplete=only_incomplete,
        statuses=statuses,
        limit=limit,
    )


def claim_ingester_scan_request(*, ingester: str) -> dict[str, Any] | None:
    """Claim the next pending manual ingester scan request when configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return None
    return store.claim_scan_request(ingester=ingester)


def complete_ingester_scan_request(
    *,
    ingester: str,
    request_token: str,
    error_message: str | None = None,
) -> None:
    """Mark one claimed ingester scan request completed when configured."""

    store = get_runtime_status_store()
    if store is None or not store.enabled:
        return
    store.complete_scan_request(
        ingester=ingester,
        request_token=request_token,
        error_message=error_message,
    )


def reset_runtime_status_store_for_tests() -> None:
    """Clear the shared runtime status store singleton."""

    global _STORE
    with _STORE_LOCK:
        if _STORE is not None and getattr(_STORE, "_conn", None) is not None:
            try:
                _STORE._conn.close()
            except Exception:
                pass
        _STORE = None
