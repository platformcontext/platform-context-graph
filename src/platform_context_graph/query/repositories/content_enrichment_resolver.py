"""Repository-resolution helpers for content enrichment."""

from __future__ import annotations

from typing import Any
from typing import Callable


def build_related_repo_resolver(
    db_manager: Any,
    resolve_related_repo: Callable[[Any, str], dict[str, Any] | None],
) -> Callable[[str], dict[str, Any] | None]:
    """Return a callable that resolves related repositories in fresh sessions."""

    def _resolve_repo(candidate: str) -> dict[str, Any] | None:
        """Resolve one related repository candidate within a short-lived session."""

        with db_manager.get_driver().session() as session:
            return resolve_related_repo(session, candidate)

    return _resolve_repo


__all__ = ["build_related_repo_resolver"]
