"""Session helpers for graph persistence transactions."""

from __future__ import annotations

from typing import Any


def begin_transaction(session: Any) -> tuple[Any, bool]:
    """Begin an explicit transaction when the backend supports it."""

    begin = getattr(session, "begin_transaction", None)
    if begin is not None:
        try:
            return begin(), True
        except (AttributeError, NotImplementedError, RuntimeError, TypeError):
            pass
    return session, False


__all__ = ["begin_transaction"]
