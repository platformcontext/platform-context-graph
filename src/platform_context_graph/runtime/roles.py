"""Runtime role helpers for split API and worker processes."""

from __future__ import annotations

import os

__all__ = [
    "get_runtime_role",
    "runtime_supports_mutations",
    "workspace_fallback_enabled",
]

_VALID_ROLES = {"api", "worker", "combined"}
_FALSEY = {"0", "false", "no", "off"}


def get_runtime_role() -> str:
    """Return the configured runtime role.

    Returns:
        One of ``api``, ``worker``, or ``combined``. Unknown values fall back to
        ``combined`` for compatibility with existing local flows.
    """

    raw = os.getenv("PCG_RUNTIME_ROLE", "combined").strip().lower()
    if raw in _VALID_ROLES:
        return raw
    return "combined"


def runtime_supports_mutations() -> bool:
    """Return whether the current runtime should expose mutating operations."""

    return get_runtime_role() != "api"


def workspace_fallback_enabled() -> bool:
    """Return whether direct workspace content fallback should be enabled."""

    raw = os.getenv("PCG_CONTENT_WORKSPACE_FALLBACK_ENABLED")
    if raw is not None:
        return raw.strip().lower() not in _FALSEY
    return get_runtime_role() != "api"
