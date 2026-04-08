"""Typed contracts for declarative framework semantic packs."""

from __future__ import annotations

from typing import Any, Final, Literal, TypedDict

FrameworkPackStrategy = Literal[
    "react_module",
    "nextjs_app_router",
    "node_http_routes",
]
SUPPORTED_FRAMEWORK_PACK_STRATEGIES: Final[set[FrameworkPackStrategy]] = {
    "react_module",
    "nextjs_app_router",
    "node_http_routes",
}


class FrameworkPackSpec(TypedDict, total=False):
    """One framework semantic pack loaded from YAML."""

    framework: str
    title: str
    strategy: FrameworkPackStrategy
    compute_order: int
    surface_order: int
    config: dict[str, Any]
    spec_path: str
