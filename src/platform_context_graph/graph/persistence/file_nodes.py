"""Shared File-node property helpers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FILE_NODE_MERGE_QUERY = """
MERGE (f:File {path: $file_path})
SET f.name = $name,
    f.relative_path = $relative_path,
    f.lang = $language,
    f.is_dependency = $is_dependency,
    f.frameworks = $frameworks,
    f.react_boundary = $react_boundary,
    f.react_component_exports = $react_component_exports,
    f.react_hooks_used = $react_hooks_used,
    f.next_module_kind = $next_module_kind,
    f.next_route_verbs = $next_route_verbs,
    f.next_metadata_exports = $next_metadata_exports,
    f.next_route_segments = $next_route_segments,
    f.next_runtime_boundary = $next_runtime_boundary,
    f.next_request_response_apis = $next_request_response_apis
"""


def build_file_node_write_params(
    *,
    file_path: str,
    name: str,
    relative_path: str,
    language: str | None,
    is_dependency: bool,
    file_data: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the full parameter payload for one File-node write."""

    params = {
        "file_path": file_path,
        "name": name,
        "relative_path": relative_path,
        "language": language,
        "is_dependency": is_dependency,
    }
    params.update(_framework_semantic_properties(file_data))
    return params


def _framework_semantic_properties(
    file_data: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Flatten parsed framework semantics into bounded File-node properties."""

    semantics = file_data.get("framework_semantics") if file_data else None
    if not isinstance(semantics, Mapping):
        return _empty_framework_semantic_properties()

    react = semantics.get("react")
    react_mapping = react if isinstance(react, Mapping) else {}
    nextjs = semantics.get("nextjs")
    nextjs_mapping = nextjs if isinstance(nextjs, Mapping) else {}
    return {
        "frameworks": _normalized_string_list(semantics.get("frameworks")),
        "react_boundary": _normalized_string(react_mapping.get("boundary")),
        "react_component_exports": _normalized_string_list(
            react_mapping.get("component_exports")
        ),
        "react_hooks_used": _normalized_string_list(react_mapping.get("hooks_used")),
        "next_module_kind": _normalized_string(nextjs_mapping.get("module_kind")),
        "next_route_verbs": _normalized_string_list(nextjs_mapping.get("route_verbs")),
        "next_metadata_exports": _normalized_string(
            nextjs_mapping.get("metadata_exports")
        ),
        "next_route_segments": _normalized_string_list(
            nextjs_mapping.get("route_segments")
        ),
        "next_runtime_boundary": _normalized_string(
            nextjs_mapping.get("runtime_boundary")
        ),
        "next_request_response_apis": _normalized_string_list(
            nextjs_mapping.get("request_response_apis")
        ),
    }


def _empty_framework_semantic_properties() -> dict[str, Any]:
    """Return the null/default payload used to clear framework properties."""

    return {
        "frameworks": None,
        "react_boundary": None,
        "react_component_exports": None,
        "react_hooks_used": None,
        "next_module_kind": None,
        "next_route_verbs": None,
        "next_metadata_exports": None,
        "next_route_segments": None,
        "next_runtime_boundary": None,
        "next_request_response_apis": None,
    }


def _normalized_string(value: object) -> str | None:
    """Return one non-empty string value when available."""

    if not isinstance(value, str):
        return None
    return value or None


def _normalized_string_list(value: object) -> list[str] | None:
    """Return a deduplicated list of non-empty strings while preserving order."""

    if value is None:
        return None
    if not isinstance(value, list | tuple):
        return None

    items: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item or item in seen:
            continue
        seen.add(item)
        items.append(item)
    return items


__all__ = ["FILE_NODE_MERGE_QUERY", "build_file_node_write_params"]
