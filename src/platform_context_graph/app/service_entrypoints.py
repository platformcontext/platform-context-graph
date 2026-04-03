"""Thin app-level service entrypoint placeholders for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass

from .roles import (
    SERVICE_ROLE_API,
    SERVICE_ROLE_GIT_COLLECTOR,
    SERVICE_ROLE_RESOLUTION_ENGINE,
)


@dataclass(frozen=True)
class ServiceEntrypointSpec:
    """Describe one Phase 1 service role boundary."""

    service_role: str
    runtime_role: str
    import_path: str
    implemented: bool


_SERVICE_ENTRYPOINTS = {
    SERVICE_ROLE_API: ServiceEntrypointSpec(
        service_role=SERVICE_ROLE_API,
        runtime_role="api",
        import_path="platform_context_graph.cli.main:start_http_api",
        implemented=True,
    ),
    SERVICE_ROLE_GIT_COLLECTOR: ServiceEntrypointSpec(
        service_role=SERVICE_ROLE_GIT_COLLECTOR,
        runtime_role="ingester",
        import_path="platform_context_graph.runtime.ingester:run_repo_sync_loop",
        implemented=True,
    ),
    SERVICE_ROLE_RESOLUTION_ENGINE: ServiceEntrypointSpec(
        service_role=SERVICE_ROLE_RESOLUTION_ENGINE,
        runtime_role="combined",
        import_path=(
            "platform_context_graph.resolution.orchestration.runtime:"
            "start_resolution_engine"
        ),
        implemented=True,
    ),
}


def get_service_entrypoint(service_role: str) -> ServiceEntrypointSpec:
    """Return the declared entrypoint metadata for one service role.

    Args:
        service_role: The logical Phase 1 service role name.

    Returns:
        The service entrypoint specification.

    Raises:
        ValueError: If the service role is unknown.
    """

    try:
        return _SERVICE_ENTRYPOINTS[service_role]
    except KeyError as exc:
        raise ValueError(f"Unknown service role: {service_role}") from exc


__all__ = [
    "ServiceEntrypointSpec",
    "get_service_entrypoint",
]
