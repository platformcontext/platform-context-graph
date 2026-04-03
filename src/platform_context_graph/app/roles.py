"""App-scoped service role constants for future service entrypoints."""

from __future__ import annotations

SERVICE_ROLE_API = "api"
SERVICE_ROLE_GIT_COLLECTOR = "git-collector"
SERVICE_ROLE_RESOLUTION_ENGINE = "resolution-engine"
SERVICE_ROLES = (
    SERVICE_ROLE_API,
    SERVICE_ROLE_GIT_COLLECTOR,
    SERVICE_ROLE_RESOLUTION_ENGINE,
)

__all__ = [
    "SERVICE_ROLE_API",
    "SERVICE_ROLE_GIT_COLLECTOR",
    "SERVICE_ROLE_RESOLUTION_ENGINE",
    "SERVICE_ROLES",
]
