"""Framework semantic facts for JavaScript and TypeScript parser results."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from .framework_packs import load_framework_pack_specs
from .framework_packs.models import FrameworkPackSpec
from .framework_packs.strategies import (
    build_nextjs_semantics,
    build_node_http_semantics,
    build_provider_sdk_semantics,
    build_python_web_semantics,
    build_react_semantics,
)


def build_framework_semantics(
    path: Path,
    source_code: str,
    *,
    parser_language: str | None = None,
    imports: list[dict[str, Any]],
    functions: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    variables: list[dict[str, Any]] | None = None,
    classes: list[dict[str, Any]] | None = None,
    components: list[dict[str, Any]] | None = None,
    pack_specs: list[FrameworkPackSpec] | None = None,
) -> dict[str, Any]:
    """Build bounded framework facts for one parsed JS/TS module."""

    resolved_specs = _filter_framework_pack_specs(
        pack_specs or list(_default_framework_pack_specs()),
        parser_language=parser_language,
    )
    computed: dict[str, dict[str, Any] | None] = {}
    for pack_spec in sorted(
        resolved_specs, key=lambda item: int(item.get("compute_order", 0))
    ):
        framework = str(pack_spec.get("framework", ""))
        strategy = pack_spec.get("strategy")
        if strategy == "react_module":
            computed[framework] = build_react_semantics(
                path,
                source_code,
                imports=imports,
                functions=functions,
                function_calls=function_calls,
                classes=classes or [],
                components=components or [],
                pack_spec=pack_spec,
            )
        elif strategy == "nextjs_app_router":
            computed[framework] = build_nextjs_semantics(
                path,
                source_code,
                imports=imports,
                react=computed.get("react"),
                pack_spec=pack_spec,
            )
        elif strategy == "node_http_routes":
            computed[framework] = build_node_http_semantics(
                path,
                source_code,
                imports=imports,
                function_calls=function_calls,
                variables=variables or [],
                pack_spec=pack_spec,
            )
        elif strategy == "python_web_routes":
            computed[framework] = build_python_web_semantics(
                path,
                source_code,
                imports=imports,
                variables=variables or [],
                pack_spec=pack_spec,
            )
        elif strategy == "provider_sdk_usage":
            computed[framework] = build_provider_sdk_semantics(
                path,
                source_code,
                imports=imports,
                function_calls=function_calls,
                pack_spec=pack_spec,
            )

    frameworks: list[str] = []
    semantics: dict[str, Any] = {"frameworks": frameworks}
    for pack_spec in sorted(
        resolved_specs, key=lambda item: int(item.get("surface_order", 0))
    ):
        framework = str(pack_spec.get("framework", ""))
        facts = computed.get(framework)
        if facts is None:
            continue
        frameworks.append(framework)
        semantics[framework] = facts
    return semantics


@lru_cache(maxsize=1)
def _default_framework_pack_specs() -> tuple[FrameworkPackSpec, ...]:
    """Load the default framework pack set once per process."""

    return tuple(load_framework_pack_specs())


def _filter_framework_pack_specs(
    pack_specs: list[FrameworkPackSpec],
    *,
    parser_language: str | None,
) -> list[FrameworkPackSpec]:
    """Return framework packs that apply to the current parser lane."""

    if not parser_language:
        return list(pack_specs)
    return [
        pack_spec
        for pack_spec in pack_specs
        if _pack_applies_to_language(pack_spec, parser_language=parser_language)
    ]


def _pack_applies_to_language(
    pack_spec: FrameworkPackSpec,
    *,
    parser_language: str,
) -> bool:
    """Return whether one framework pack applies to the current parser lane."""

    languages = pack_spec.get("languages")
    if not isinstance(languages, list) or not languages:
        return True
    return parser_language in languages


__all__ = ["build_framework_semantics"]
