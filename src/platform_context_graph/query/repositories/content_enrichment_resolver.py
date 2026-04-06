"""Repository-resolution helpers for content enrichment."""

from __future__ import annotations

from typing import Any
from typing import Callable

from .common import resolve_repository


def build_related_repo_resolver(
    db_manager: Any,
) -> Callable[[str], dict[str, Any] | None]:
    """Return a callable that resolves related repositories in fresh sessions."""

    def _resolve_repo(candidate: str) -> dict[str, Any] | None:
        """Resolve one related repository candidate within a short-lived session."""

        with db_manager.get_driver().session() as session:
            return _resolve_related_repo(session, candidate)

    return _resolve_repo


def _resolve_related_repo(session: Any, candidate: str) -> dict[str, Any] | None:
    """Resolve one related repository candidate against the graph."""

    normalized = candidate.strip()
    if not normalized:
        return None
    return resolve_repository(session, normalized)


__all__ = ["build_related_repo_resolver"]
