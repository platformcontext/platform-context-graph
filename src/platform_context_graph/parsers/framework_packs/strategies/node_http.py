"""Node HTTP framework-pack strategy helpers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from ..models import FrameworkPackSpec
from .support import (
    config_list,
    imports_any_source,
    ordered_unique,
    pack_config,
    strip_js_comments,
)


def build_node_http_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    variables: list[dict[str, Any]],
    pack_spec: FrameworkPackSpec,
) -> dict[str, Any] | None:
    """Build bounded Node HTTP semantics for one module."""

    del path
    config = pack_config(pack_spec)
    normalized_source = strip_js_comments(source_code)
    server_symbols = _collect_server_symbols(
        imports,
        variables,
        framework_import_sources=config_list(
            config, "framework_import_sources", default=[]
        ),
        server_variable_values=config_list(
            config, "server_variable_values", default=[]
        ),
    )
    route_methods = _collect_route_methods(
        normalized_source,
        function_calls,
        route_call_names=config_list(config, "route_call_names", default=[]),
        route_object_method_pattern=config_list(
            config,
            "route_object_method_patterns",
            default=[],
        ),
        server_symbols=server_symbols,
    )
    route_paths = _collect_route_paths(
        normalized_source,
        function_calls,
        route_call_names=config_list(config, "route_call_names", default=[]),
        route_object_path_pattern=config_list(
            config,
            "route_object_path_patterns",
            default=[],
        ),
        server_symbols=server_symbols,
    )
    require_methods_and_paths = bool(config.get("require_methods_and_paths"))
    if require_methods_and_paths and (not route_methods or not route_paths):
        return None
    if not route_methods and not route_paths:
        return None
    return {
        "route_methods": route_methods,
        "route_paths": route_paths,
        "server_symbols": server_symbols,
    }


def _collect_server_symbols(
    imports: list[dict[str, Any]],
    variables: list[dict[str, Any]],
    *,
    framework_import_sources: list[str],
    server_variable_values: list[str],
) -> list[str]:
    """Collect configured app/router/server variable symbols."""

    if not imports_any_source(imports, sources=framework_import_sources):
        return []
    allowed_values = set(server_variable_values)
    return ordered_unique(
        str(item["name"])
        for item in variables
        if isinstance(item.get("name"), str) and item.get("value") in allowed_values
    )


def _collect_route_methods(
    source_code: str,
    function_calls: list[dict[str, Any]],
    *,
    route_call_names: list[str],
    route_object_method_pattern: list[str],
    server_symbols: list[str],
) -> list[str]:
    """Collect route methods from call-style and object-style route definitions."""

    methods: list[str] = []
    methods.extend(
        _collect_call_route_methods(
            function_calls,
            route_call_names=route_call_names,
            server_symbols=server_symbols,
        )
    )

    for pattern in route_object_method_pattern:
        for match in re.findall(pattern, source_code, re.MULTILINE):
            methods.extend(_extract_quoted_tokens(match))
    return ordered_unique(methods)


def _collect_route_paths(
    source_code: str,
    function_calls: list[dict[str, Any]],
    *,
    route_call_names: list[str],
    route_object_path_pattern: list[str],
    server_symbols: list[str],
) -> list[str]:
    """Collect route paths from call-style and object-style route definitions."""

    paths: list[str] = []
    paths.extend(
        _collect_call_route_paths(
            function_calls,
            route_call_names=route_call_names,
            server_symbols=server_symbols,
        )
    )

    for pattern in route_object_path_pattern:
        for match in re.findall(pattern, source_code, re.MULTILINE):
            path = _strip_string_wrapper(match)
            if path is not None and _looks_like_http_route_path(path):
                paths.append(path)
    return ordered_unique(paths)


def _extract_quoted_tokens(value: str) -> list[str]:
    """Extract quoted method tokens from a string or array literal."""

    return [token.upper() for token in re.findall(r"['\"]([A-Za-z]+)['\"]", value)]


def _collect_call_route_methods(
    function_calls: list[dict[str, Any]],
    *,
    route_call_names: list[str],
    server_symbols: list[str],
) -> list[str]:
    """Collect route methods from call-style framework APIs."""

    if not route_call_names or not server_symbols:
        return []

    methods: list[str] = []
    allowed_call_names = set(name.lower() for name in route_call_names)
    allowed_symbols = set(server_symbols)
    for call in function_calls:
        name = str(call.get("name") or "").lower()
        full_name = str(call.get("full_name") or "")
        if name not in allowed_call_names:
            continue
        if not any(full_name.startswith(f"{symbol}.") for symbol in allowed_symbols):
            continue
        methods.append(name.upper())
    return ordered_unique(methods)


def _collect_call_route_paths(
    function_calls: list[dict[str, Any]],
    *,
    route_call_names: list[str],
    server_symbols: list[str],
) -> list[str]:
    """Collect route paths from call-style framework APIs."""

    if not route_call_names or not server_symbols:
        return []

    paths: list[str] = []
    allowed_call_names = set(name.lower() for name in route_call_names)
    allowed_symbols = set(server_symbols)
    for call in function_calls:
        name = str(call.get("name") or "").lower()
        full_name = str(call.get("full_name") or "")
        if name not in allowed_call_names:
            continue
        if not any(full_name.startswith(f"{symbol}.") for symbol in allowed_symbols):
            continue
        args = call.get("args") or []
        if not args:
            continue
        path = _strip_string_wrapper(str(args[0]))
        if path is not None and _looks_like_http_route_path(path):
            paths.append(path)
    return ordered_unique(paths)


def _strip_string_wrapper(value: str) -> str | None:
    """Remove matching quote/backtick wrappers from a string literal."""

    stripped = value.strip()
    if len(stripped) < 2:
        return None
    if stripped[0] != stripped[-1]:
        return None
    if stripped[0] not in {"'", '"', "`"}:
        return None
    return stripped[1:-1]


def _looks_like_http_route_path(value: str) -> bool:
    """Return whether one string literal looks like an HTTP route path."""

    return value.startswith("/")
