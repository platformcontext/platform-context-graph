"""React and Next.js framework-pack strategy helpers."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from ..models import FrameworkPackSpec
from .support import (
    compile_patterns,
    config_list,
    config_string,
    imports_any_source,
    ordered_unique,
    pack_config,
)


def build_react_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    functions: list[dict[str, Any]],
    function_calls: list[dict[str, Any]],
    classes: list[dict[str, Any]],
    components: list[dict[str, Any]],
    pack_spec: FrameworkPackSpec,
) -> dict[str, Any] | None:
    """Build React-specific semantic facts from one declarative pack."""

    config = pack_config(pack_spec)
    boundary = _detect_boundary(
        source_code,
        boundary_directives=config_list(
            config, "boundary_directives", default=["client", "server"]
        ),
    )
    hooks_used = _collect_hook_names(
        imports,
        function_calls,
        hook_name_pattern=config_string(
            config, "hook_name_pattern", default=r"^use[A-Z][A-Za-z0-9]*$"
        ),
    )
    component_exports = _find_component_exports(
        source_code,
        available_names={
            item["name"]
            for item in [*functions, *classes, *components]
            if isinstance(item.get("name"), str)
        },
        is_react_candidate=(
            path.suffix
            in set(
                config_list(
                    config, "react_candidate_path_suffixes", default=[".jsx", ".tsx"]
                )
            )
            or imports_any_source(
                imports,
                sources=config_list(
                    config, "react_candidate_import_sources", default=["react"]
                ),
            )
            or bool(hooks_used)
            or any(
                segment in path.parts
                for segment in config_list(
                    config, "react_candidate_path_segments", default=["components"]
                )
            )
        ),
        component_name_pattern=config_string(
            config, "component_name_pattern", default=r"^[A-Z][A-Za-z0-9]*$"
        ),
        component_export_patterns=config_list(
            config,
            "component_export_patterns",
            default=[
                r"^\s*export\s+default\s+(?:async\s+)?function\s+([A-Z][A-Za-z0-9]*)\b",
                r"^\s*export\s+(?:async\s+)?function\s+([A-Z][A-Za-z0-9]*)\b",
                r"^\s*export\s+const\s+([A-Z][A-Za-z0-9]*)\b",
                r"^\s*export\s+class\s+([A-Z][A-Za-z0-9]*)\b",
                r"^\s*export\s+default\s+([A-Z][A-Za-z0-9]*)\b",
            ],
        ),
    )
    if boundary == "shared" and not hooks_used and not component_exports:
        return None
    return {
        "boundary": boundary,
        "component_exports": component_exports,
        "hooks_used": hooks_used,
    }


def build_nextjs_semantics(
    path: Path,
    source_code: str,
    *,
    imports: list[dict[str, Any]],
    react: dict[str, Any] | None,
    pack_spec: FrameworkPackSpec,
) -> dict[str, Any] | None:
    """Build Next.js-specific semantic facts from one declarative pack."""

    config = pack_config(pack_spec)
    module_kind, route_segments = _module_kind_and_segments(
        path,
        module_root_segments=config_list(
            config, "module_root_segments", default=["app"]
        ),
        module_kinds=config_list(
            config, "module_kinds", default=["page", "layout", "route"]
        ),
    )
    route_verbs = _collect_route_verbs(
        source_code,
        route_verbs=config_list(
            config,
            "route_verbs",
            default=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
        ),
    )
    metadata_exports = _metadata_exports(
        source_code,
        static_patterns=config_list(
            config,
            "static_metadata_patterns",
            default=[r"^\s*export\s+const\s+metadata\b"],
        ),
        dynamic_patterns=config_list(
            config,
            "dynamic_metadata_patterns",
            default=[r"^\s*export\s+(?:async\s+)?function\s+generateMetadata\b"],
        ),
    )
    request_response_apis = _request_response_apis(
        imports,
        source_code,
        import_sources=config_list(
            config,
            "request_response_import_sources",
            default=["next", "next/server"],
        ),
        api_names=config_list(
            config,
            "request_response_api_names",
            default=["NextRequest", "NextResponse"],
        ),
    )

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


def _detect_boundary(source_code: str, *, boundary_directives: list[str]) -> str:
    """Detect a top-level React/Next runtime directive."""

    directive = None
    in_block_comment = False
    pattern = re.compile(
        r"""^['"]use ("""
        + "|".join(re.escape(item) for item in boundary_directives)
        + r""")['"];?$"""
    )
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
        match = pattern.match(line)
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
    *,
    hook_name_pattern: str,
) -> list[str]:
    """Collect imported or called hook-like names in source order."""

    hook_re = re.compile(hook_name_pattern)
    hooks: list[str] = []
    for item in imports:
        for candidate in (item.get("alias"), item.get("name")):
            if isinstance(candidate, str) and hook_re.match(candidate):
                hooks.append(candidate)
    for item in function_calls:
        candidate = item.get("name")
        if isinstance(candidate, str) and hook_re.match(candidate):
            hooks.append(candidate)
    return ordered_unique(hooks)


def _find_component_exports(
    source_code: str,
    *,
    available_names: set[str],
    is_react_candidate: bool,
    component_name_pattern: str,
    component_export_patterns: list[str],
) -> list[str]:
    """Find exported PascalCase component names in source order."""

    if not is_react_candidate:
        return []

    component_name_re = re.compile(component_name_pattern)
    exported_names: list[str] = []
    for pattern in compile_patterns(tuple(component_export_patterns)):
        exported_names.extend(pattern.findall(source_code))
    return ordered_unique(
        name
        for name in exported_names
        if component_name_re.match(name) and name in available_names
    )


def _module_kind_and_segments(
    path: Path,
    *,
    module_root_segments: list[str],
    module_kinds: list[str],
) -> tuple[str | None, list[str]]:
    """Return the configured module kind and route segments."""

    parts = path.parts
    root_indexes = [
        index for index, part in enumerate(parts) if part in set(module_root_segments)
    ]
    if not root_indexes:
        return None, []
    root_index = max(root_indexes)
    if root_index >= len(parts) - 1:
        return None, []

    stem = path.stem
    if stem not in set(module_kinds):
        return None, []
    return stem, list(parts[root_index + 1 : -1])


def _collect_route_verbs(source_code: str, *, route_verbs: list[str]) -> list[str]:
    """Collect exported HTTP-like verb handlers in source order."""

    if not route_verbs:
        return []
    pattern = re.compile(
        r"^\s*export\s+(?:async\s+)?function\s+("
        + "|".join(re.escape(item) for item in route_verbs)
        + r")\b",
        re.MULTILINE,
    )
    return ordered_unique(pattern.findall(source_code))


def _metadata_exports(
    source_code: str,
    *,
    static_patterns: list[str],
    dynamic_patterns: list[str],
) -> str:
    """Classify configured metadata export styles for one module."""

    has_static = any(
        pattern.search(source_code)
        for pattern in compile_patterns(tuple(static_patterns))
    )
    has_dynamic = any(
        pattern.search(source_code)
        for pattern in compile_patterns(tuple(dynamic_patterns))
    )
    if has_static and has_dynamic:
        return "both"
    if has_static:
        return "static"
    if has_dynamic:
        return "dynamic"
    return "none"


def _request_response_apis(
    imports: list[dict[str, Any]],
    source_code: str,
    *,
    import_sources: list[str],
    api_names: list[str],
) -> list[str]:
    """Collect configured request/response API names from imports and source."""

    names: list[str] = []
    allowed_sources = set(import_sources)
    allowed_names = set(api_names)
    has_matching_import_source = False
    for item in imports:
        if item.get("source") not in allowed_sources:
            continue
        has_matching_import_source = True
        for candidate in (item.get("alias"), item.get("name")):
            if candidate in allowed_names:
                names.append(str(candidate))
    if has_matching_import_source:
        for name in api_names:
            if name in source_code:
                names.append(name)
    return ordered_unique(names)
