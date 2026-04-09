"""Python web framework-pack strategy helpers."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from ..models import FrameworkPackSpec
from .support import config_list, ordered_unique, pack_config


def build_python_web_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    variables: list[dict[str, Any]],
    pack_spec: FrameworkPackSpec,
) -> dict[str, Any] | None:
    """Build bounded FastAPI/Flask semantics for one Python module."""

    del path, variables
    config = pack_config(pack_spec)
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    constructor_names = _configured_constructor_names(imports, config=config)
    symbol_prefixes, known_symbols = _collect_server_symbols(
        tree,
        constructor_names=constructor_names,
        prefix_keyword_names=config_list(config, "prefix_keyword_names", default=[]),
    )
    route_decorator_map = _route_decorator_map(config.get("route_decorator_map"))
    default_methods = config_list(config, "default_methods", default=[])
    require_known_server_symbol = bool(config.get("require_known_server_symbol"))
    allow_unknown_decorator_names = set(
        config_list(config, "allow_unknown_decorator_names", default=[])
    )

    route_methods: list[str] = []
    route_paths: list[str] = []
    server_symbols: list[str] = []
    for function_node in ast.walk(tree):
        if not isinstance(function_node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for route in _collect_function_routes(
            function_node,
            symbol_prefixes=symbol_prefixes,
            known_symbols=known_symbols,
            route_decorator_map=route_decorator_map,
            default_methods=default_methods,
            require_known_server_symbol=require_known_server_symbol,
            allow_unknown_decorator_names=allow_unknown_decorator_names,
        ):
            route_methods.extend(route["methods"])
            route_paths.append(route["path"])
            server_symbols.append(route["symbol"])

    if not route_methods and not route_paths:
        return None
    return {
        "route_methods": ordered_unique(route_methods),
        "route_paths": ordered_unique(route_paths),
        "server_symbols": ordered_unique(server_symbols),
    }


def _configured_constructor_names(
    imports: list[dict[str, Any]],
    *,
    config: dict[str, Any],
) -> set[str]:
    """Return configured constructor names plus imported aliases."""

    constructor_names = set(config_list(config, "constructor_names", default=[]))
    import_full_names = set(config_list(config, "import_full_names", default=[]))
    factory_function_names = set(
        config_list(config, "factory_function_names", default=[])
    )
    for item in imports:
        full_import_name = item.get("full_import_name")
        name = item.get("name")
        alias = item.get("alias")
        matches_framework_constructor = full_import_name in import_full_names
        imported_leaf = (
            full_import_name.rsplit(".", maxsplit=1)[-1]
            if isinstance(full_import_name, str)
            else None
        )
        matches_factory_name = (
            imported_leaf in factory_function_names
            or name in factory_function_names
            or alias in factory_function_names
        )
        if not matches_framework_constructor and not matches_factory_name:
            continue
        if isinstance(name, str) and name:
            constructor_names.add(name)
        if isinstance(alias, str) and alias:
            constructor_names.add(alias)
    return constructor_names


def _collect_server_symbols(
    tree: ast.AST,
    *,
    constructor_names: set[str],
    prefix_keyword_names: list[str],
) -> tuple[dict[str, str], set[str]]:
    """Return route symbol prefixes and the known route-owner symbols."""

    symbol_prefixes: dict[str, str] = {}
    known_symbols: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign | ast.AnnAssign):
            continue
        value_node = node.value
        if not isinstance(value_node, ast.Call):
            continue
        constructor_name = _call_name(value_node.func)
        if constructor_name not in constructor_names:
            continue
        prefix = ""
        for keyword in value_node.keywords:
            if keyword.arg not in prefix_keyword_names:
                continue
            literal = _string_literal(keyword.value)
            if literal and literal.startswith("/"):
                prefix = literal
                break
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                known_symbols.add(target.id)
                symbol_prefixes[target.id] = prefix
    return symbol_prefixes, known_symbols


def _collect_function_routes(
    function_node: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    symbol_prefixes: dict[str, str],
    known_symbols: set[str],
    route_decorator_map: dict[str, list[str]],
    default_methods: list[str],
    require_known_server_symbol: bool,
    allow_unknown_decorator_names: set[str],
) -> list[dict[str, Any]]:
    """Collect bounded route facts from one decorated function."""

    routes: list[dict[str, Any]] = []
    for decorator in function_node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        if not isinstance(decorator.func, ast.Attribute):
            continue
        if not isinstance(decorator.func.value, ast.Name):
            continue
        symbol = decorator.func.value.id
        decorator_name = decorator.func.attr
        if decorator_name not in route_decorator_map:
            continue
        if require_known_server_symbol and symbol not in known_symbols:
            continue
        if (
            symbol not in known_symbols
            and decorator_name not in allow_unknown_decorator_names
        ):
            continue
        if not decorator.args:
            continue
        route_path = _string_literal(decorator.args[0])
        if not route_path or not route_path.startswith("/"):
            continue
        methods = route_decorator_map[decorator_name] or _methods_keyword(
            decorator, default_methods=default_methods
        )
        if not methods:
            continue
        routes.append(
            {
                "symbol": symbol,
                "methods": methods,
                "path": _join_route_parts(symbol_prefixes.get(symbol, ""), route_path),
            }
        )
    return routes


def _route_decorator_map(value: object) -> dict[str, list[str]]:
    """Return a normalized decorator-to-method mapping."""

    if not isinstance(value, dict):
        return {}
    mapping: dict[str, list[str]] = {}
    for key, methods in value.items():
        if not isinstance(key, str):
            continue
        if not isinstance(methods, list):
            continue
        mapping[key] = [
            method.upper()
            for method in methods
            if isinstance(method, str) and method.strip()
        ]
    return mapping


def _methods_keyword(
    decorator: ast.Call,
    *,
    default_methods: list[str],
) -> list[str]:
    """Return route methods from a decorator keyword or its configured default."""

    for keyword in decorator.keywords:
        if keyword.arg != "methods":
            continue
        if isinstance(keyword.value, ast.List | ast.Tuple):
            methods = [
                literal.upper()
                for item in keyword.value.elts
                if (literal := _string_literal(item))
            ]
            return ordered_unique(methods)
    return ordered_unique([method.upper() for method in default_methods])


def _call_name(node: ast.AST) -> str | None:
    """Return the leaf name for a constructor or decorator target."""

    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


def _string_literal(node: ast.AST) -> str | None:
    """Return a string literal value from one AST node when available."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _join_route_parts(prefix: str, path: str) -> str:
    """Join one optional route prefix with one route path."""

    if not prefix:
        return path
    return f"{prefix.rstrip('/')}/{path.lstrip('/')}"
