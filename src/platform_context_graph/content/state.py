"""Global state helpers for content-store providers."""

from __future__ import annotations

import os
import threading

from typing import Any

from ..runtime.roles import workspace_fallback_enabled
from .postgres import PostgresContentProvider
from .service import ContentService
from .workspace import WorkspaceContentProvider

__all__ = [
    "get_content_service",
    "get_postgres_content_provider",
    "reset_content_store_for_tests",
]

_LOCK = threading.Lock()
_POSTGRES_PROVIDER: PostgresContentProvider | None = None


def _content_store_enabled() -> bool:
    """Return whether the content store is enabled by configuration.

    Returns:
        ``True`` when the content store should attempt to use PostgreSQL.
    """

    raw = os.getenv("PCG_CONTENT_STORE_ENABLED", "true").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def _content_store_dsn() -> str | None:
    """Return the configured PostgreSQL DSN, if any.

    Returns:
        Configured DSN string or ``None``.
    """

    for key in ("PCG_CONTENT_STORE_DSN", "PCG_POSTGRES_DSN"):
        value = os.getenv(key)
        if value and value.strip():
            return value.strip()
    return None


def get_postgres_content_provider() -> PostgresContentProvider | None:
    """Return the shared PostgreSQL content provider when configured.

    Returns:
        Shared provider instance or ``None`` when the content store is disabled.
    """

    global _POSTGRES_PROVIDER
    if not _content_store_enabled():
        return None

    dsn = _content_store_dsn()
    if not dsn:
        return None

    with _LOCK:
        if _POSTGRES_PROVIDER is None:
            _POSTGRES_PROVIDER = PostgresContentProvider(dsn)
        return _POSTGRES_PROVIDER


def get_content_service(database: Any) -> ContentService:
    """Build the content service for one query invocation.

    Args:
        database: Database dependency used for workspace fallback lookups.

    Returns:
        Content service combining PostgreSQL and workspace providers.
    """

    workspace_provider = (
        WorkspaceContentProvider(database) if workspace_fallback_enabled() else None
    )
    return ContentService(
        postgres_provider=get_postgres_content_provider(),
        workspace_provider=workspace_provider,
    )


def reset_content_store_for_tests() -> None:
    """Clear the shared PostgreSQL provider used by tests."""

    global _POSTGRES_PROVIDER
    with _LOCK:
        if _POSTGRES_PROVIDER is not None:
            _POSTGRES_PROVIDER.close()
        _POSTGRES_PROVIDER = None
