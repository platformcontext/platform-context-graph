"""Shared state helpers for the repository relationship store."""

from __future__ import annotations

import os
import threading

from .postgres import PostgresRelationshipStore

__all__ = ["get_relationship_store", "reset_relationship_store_for_tests"]

_LOCK = threading.Lock()
_STORE: PostgresRelationshipStore | None = None


def _relationship_store_enabled() -> bool:
    raw = os.getenv("PCG_RELATIONSHIP_STORE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _relationship_store_dsn() -> str | None:
    for key in (
        "PCG_RELATIONSHIP_STORE_DSN",
        "PCG_CONTENT_STORE_DSN",
        "PCG_POSTGRES_DSN",
    ):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def get_relationship_store() -> PostgresRelationshipStore | None:
    """Return the shared relationship store when configured."""

    global _STORE
    if not _relationship_store_enabled():
        return None
    dsn = _relationship_store_dsn()
    if not dsn:
        return None
    with _LOCK:
        if _STORE is None:
            _STORE = PostgresRelationshipStore(dsn)
        return _STORE


def reset_relationship_store_for_tests() -> None:
    """Clear the shared store used across tests."""

    global _STORE
    with _LOCK:
        if _STORE is not None:
            _STORE.close()
        _STORE = None
