"""Shared runtime state helpers for the facts-first pipeline."""

from __future__ import annotations

import os
import threading

from platform_context_graph.resolution.decisions import PostgresProjectionDecisionStore

from .storage import PostgresFactStore
from .work_queue import PostgresFactWorkQueue

__all__ = [
    "facts_first_projection_enabled",
    "facts_first_indexing_enabled",
    "facts_runtime_ready",
    "get_fact_store",
    "get_fact_work_queue",
    "get_projection_decision_store",
    "git_facts_first_enabled",
    "reset_fact_runtime_for_tests",
    "reset_facts_runtime_for_tests",
]

_LOCK = threading.Lock()
_FACT_STORE: PostgresFactStore | None = None
_FACT_WORK_QUEUE: PostgresFactWorkQueue | None = None
_PROJECTION_DECISION_STORE: PostgresProjectionDecisionStore | None = None


def _facts_dsn() -> str | None:
    """Return the configured PostgreSQL DSN for facts runtime state."""

    for key in ("PCG_FACT_STORE_DSN", "PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def get_fact_store() -> PostgresFactStore | None:
    """Return the shared fact store when configured."""

    global _FACT_STORE
    dsn = _facts_dsn()
    if not dsn:
        return None

    with _LOCK:
        if _FACT_STORE is None:
            _FACT_STORE = PostgresFactStore(dsn)
        return _FACT_STORE


def get_fact_work_queue() -> PostgresFactWorkQueue | None:
    """Return the shared fact work queue when configured."""

    global _FACT_WORK_QUEUE
    dsn = _facts_dsn()
    if not dsn:
        return None

    with _LOCK:
        if _FACT_WORK_QUEUE is None:
            _FACT_WORK_QUEUE = PostgresFactWorkQueue(dsn)
        return _FACT_WORK_QUEUE


def get_projection_decision_store() -> PostgresProjectionDecisionStore | None:
    """Return the shared projection decision store when configured."""

    global _PROJECTION_DECISION_STORE
    dsn = _facts_dsn()
    if not dsn:
        return None

    with _LOCK:
        if _PROJECTION_DECISION_STORE is None:
            _PROJECTION_DECISION_STORE = PostgresProjectionDecisionStore(dsn)
        return _PROJECTION_DECISION_STORE


def facts_runtime_ready() -> bool:
    """Return whether both fact persistence and queue runtime are configured."""

    return (
        get_fact_store() is not None
        and get_fact_work_queue() is not None
        and get_projection_decision_store() is not None
    )


def git_facts_first_enabled() -> bool:
    """Return whether Git indexing should use the facts-first write path."""

    raw_value = os.getenv("PCG_GIT_FACTS_FIRST_ENABLED")
    if raw_value is not None and raw_value.strip():
        return raw_value.strip().lower() not in {"0", "false", "no", "off"}
    return facts_runtime_ready()


def facts_first_indexing_enabled() -> bool:
    """Alias for the facts-first Git indexing feature gate."""

    return git_facts_first_enabled()


def facts_first_projection_enabled() -> bool:
    """Alias for the facts-first Git projection feature gate."""

    return git_facts_first_enabled()


def reset_facts_runtime_for_tests() -> None:
    """Clear shared fact runtime state between tests."""

    global _FACT_STORE
    global _FACT_WORK_QUEUE
    global _PROJECTION_DECISION_STORE

    with _LOCK:
        if _FACT_STORE is not None:
            close_store = getattr(_FACT_STORE, "close", None)
            if callable(close_store):
                close_store()
        if _FACT_WORK_QUEUE is not None:
            close_queue = getattr(_FACT_WORK_QUEUE, "close", None)
            if callable(close_queue):
                close_queue()
        if _PROJECTION_DECISION_STORE is not None:
            close_store = getattr(_PROJECTION_DECISION_STORE, "close", None)
            if callable(close_store):
                close_store()
        _FACT_STORE = None
        _FACT_WORK_QUEUE = None
        _PROJECTION_DECISION_STORE = None


def reset_fact_runtime_for_tests() -> None:
    """Alias used by newer tests and docs."""

    reset_facts_runtime_for_tests()
