"""Framework semantic facts for JavaScript and TypeScript parser results."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

_DIRECTIVE_RE = re.compile(r"""^['"]use (client|server)['"];?$""")
_COMPONENT_NAME_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
_HOOK_NAME_RE = re.compile(r"^use[A-Z][A-Za-z0-9]*$")
_ROUTE_VERB_RE = re.compile(
    r"^\s*export\s+(?:async\s+)?function\s+"
    r"(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\b",
    re.MULTILINE,
)
_STATIC_METADATA_RE = re.compile(r"^\s*export\s+const\s+metadata\b", re.MULTILINE)
_DYNAMIC_METADATA_RE = re.compile(
    r"^\s*export\s+(?:async\s+)?function\s+generateMetadata\b",
    re.MULTILINE,
)
_COMPONENT_EXPORT_PATTERNS = (
    re.compile(
        r"^\s*export\s+default\s+(?:async\s+)?function\s+([A-Z][A-Za-z0-9]*)\b",
        re.MULTILINE,
    ),
    re.compile(
        r"^\s*export\s+(?:async\s+)?function\s+([A-Z][A-Za-z0-9]*)\b",
        re.MULTILINE,
    ),
    re.compile(r"^\s*export\s+const\s+([A-Z][A-Za-z0-9]*)\b", re.MULTILINE),
    re.compile(r"^\s*export\s+class\s+([A-Z][A-Za-z0-9]*)\b", re.MULTILINE),
    re.compile(r"^\s*export\s+default\s+([A-Z][A-Za-z0-9]*)\b", re.MULTILINE),
)
_NEXT_KINDS = {"page", "layout", "route"}
_NEXT_IMPORT_SOURCES = {"next", "next/server"}


def build_framework_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    functions: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    classes: list[dict[str, Any]] | None = None,
    components: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build bounded React and Next.js facts for one parsed module."""

    react = _build_react_semantics(
        path,
        source_code,
        imports=imports,
        functions=functions,
        function_calls=function_calls,
        classes=classes or [],
        components=components or [],
    )
    nextjs = _build_nextjs_semantics(path, source_code, imports=imports, react=react)

    frameworks: list[str] = []
    semantics: dict[str, Any] = {"frameworks": frameworks}
    if nextjs is not None:
        frameworks.append("nextjs")
        semantics["nextjs"] = nextjs
    if react is not None:
        frameworks.append("react")
        semantics["react"] = react
    return semantics


def _build_react_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    functions: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    components: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Build React-specific semantic facts for a parsed module."""

    boundary = _detect_boundary(source_code)
    hooks_used = _collect_hook_names(imports, function_calls)
    component_exports = _find_component_exports(
        source_code,
        available_names={
            item["name"]
            for item in [*functions, *classes, *components]
            if isinstance(item.get("name"), str)
        },
        is_react_candidate=(
            path.suffix in {".jsx", ".tsx"}
            or _imports_react(imports)
            or bool(hooks_used)
            or "components" in path.parts
        ),
    )
    if boundary == "shared" and not hooks_used and not component_exports:
        return None
    return {
        "boundary": boundary,
        "component_exports": component_exports,
        "hooks_used": hooks_used,
    }


def _build_nextjs_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    react: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Build Next.js-specific semantic facts for a parsed module."""

    module_kind, route_segments = _next_module_kind_and_segments(path)
    route_verbs = _ordered_unique(_ROUTE_VERB_RE.findall(source_code))
    metadata_exports = _metadata_exports(source_code)
    request_response_apis = _next_request_response_apis(imports, source_code)

    has_next_evidence = any(
        (
            module_kind is not None,
            route_verbs,
            metadata_exports != "none",
            request_response_apis,
        )
    )
    if not has_next_evidence:
        return None

    runtime_boundary = "server"
    if module_kind != "route" and react is not None:
        runtime_boundary = "client" if react["boundary"] == "client" else "server"

    return {
        "module_kind": module_kind,
        "route_verbs": route_verbs,
        "metadata_exports": metadata_exports,
        "route_segments": route_segments,
        "runtime_boundary": runtime_boundary,
        "request_response_apis": request_response_apis,
    }


def _detect_boundary(source_code: str) -> str:
    """Detect a top-level React/Next runtime directive."""

    directive = None
    in_block_comment = False
    for raw_line in source_code.lstrip("\ufeff").splitlines():
        line = raw_line.strip()
        if in_block_comment:
            if "*/" in line:
                in_block_comment = False
            continue
        if not line:
            continue
        if line.startswith("//"):
            continue
        if line.startswith("/*"):
            if "*/" not in line:
                in_block_comment = True
            continue
        match = _DIRECTIVE_RE.match(line)
        if match is not None:
            directive = match.group(1)
            continue
        break
    if directive == "client":
        return "client"
    if directive == "server":
        return "server"
    return "shared"


def _collect_hook_names(
    imports: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
) -> list[str]:
    """Collect imported or called hook-like names in source order."""

    hooks: list[str] = []
    for item in imports:
        for candidate in (item.get("alias"), item.get("name")):
            if isinstance(candidate, str) and _HOOK_NAME_RE.match(candidate):
                hooks.append(candidate)
    for item in function_calls:
        candidate = item.get("name")
        if isinstance(candidate, str) and _HOOK_NAME_RE.match(candidate):
            hooks.append(candidate)
    return _ordered_unique(hooks)


def _find_component_exports(
    source_code: str,
    *,
    available_names: set[str],
    is_react_candidate: bool,
) -> list[str]:
    """Find exported PascalCase component names in source order."""

    if not is_react_candidate:
        return []

    exported_names: list[str] = []
    for pattern in _COMPONENT_EXPORT_PATTERNS:
        exported_names.extend(pattern.findall(source_code))
    return _ordered_unique(
        name
        for name in exported_names
        if _COMPONENT_NAME_RE.match(name) and name in available_names
    )


def _imports_react(imports: list[dict[str, Any]]) -> bool:
    """Return whether the module imports React."""

    return any(item.get("source") == "react" for item in imports)


def _next_module_kind_and_segments(path: Path) -> tuple[str | None, list[str]]:
    """Return the Next.js module kind and app-router path segments."""

    parts = path.parts
    if "app" not in parts:
        return None, []
    app_index = max(index for index, part in enumerate(parts) if part == "app")
    if app_index >= len(parts) - 1:
        return None, []

    stem = path.stem
    if stem not in _NEXT_KINDS:
        return None, []
    return stem, list(parts[app_index + 1 : -1])


def _metadata_exports(source_code: str) -> str:
    """Classify Next.js metadata export style for one module."""

    has_static = bool(_STATIC_METADATA_RE.search(source_code))
    has_dynamic = bool(_DYNAMIC_METADATA_RE.search(source_code))
    if has_static and has_dynamic:
        return "both"
    if has_static:
        return "static"
    if has_dynamic:
        return "dynamic"
    return "none"


def _next_request_response_apis(
    imports: list[dict[str, Any]], source_code: str
) -> list[str]:
    """Collect Next.js request and response API imports."""

    names: list[str] = []
    has_next_server_import = False
    for item in imports:
        if item.get("source") not in _NEXT_IMPORT_SOURCES:
            continue
        has_next_server_import = True
        for candidate in (item.get("alias"), item.get("name")):
            if candidate in {"NextRequest", "NextResponse"}:
                names.append(str(candidate))
    if has_next_server_import:
        if "NextRequest" in source_code:
            names.append("NextRequest")
        if "NextResponse" in source_code:
            names.append("NextResponse")
    return _ordered_unique(names)


def _ordered_unique(values: list[str] | tuple[str, ...] | set[str] | Any) -> list[str]:
    """Return unique string values while preserving first-seen order."""

    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


__all__ = ["build_framework_semantics"]
