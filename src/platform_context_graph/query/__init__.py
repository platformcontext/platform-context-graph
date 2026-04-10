"""Canonical query-service modules for the HTTP and MCP adapters."""

from importlib import import_module

from . import (
    code,
    compare,
    content,
    context,
    entity_resolution,
    investigation,
    impact,
    infra,
    repositories,
    status,
)

__all__ = [
    "code",
    "compare",
    "content",
    "context",
    "entity_resolution",
    "investigation",
    "impact",
    "infra",
    "repositories",
    "status",
]


def __getattr__(name: str):
    """Lazily expose query submodules on explicit access."""

    qualified_name = f"{__name__}.{name}"
    try:
        module = import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
        if exc.name == qualified_name:
            raise AttributeError(
                f"module {__name__!r} has no attribute {name!r}"
            ) from exc
        raise
    globals()[name] = module
    return module
