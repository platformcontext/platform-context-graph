"""Framework-aware story helpers."""

from __future__ import annotations

from typing import Any

from .story_shared import human_list

_ROUTE_FRAMEWORK_LABELS = (
    ("express", "Express"),
    ("hapi", "Hapi"),
    ("fastapi", "FastAPI"),
    ("flask", "Flask"),
)
_PROVIDER_FRAMEWORK_LABELS = (
    ("aws", "AWS"),
    ("gcp", "GCP"),
)


def summarize_framework_overview(framework_summary: dict[str, Any] | None) -> str:
    """Return one short human-readable framework summary line."""

    if not isinstance(framework_summary, dict):
        return ""

    route_parts: list[str] = []
    provider_parts: list[str] = []
    app_parts: list[str] = []
    for framework, label in _ROUTE_FRAMEWORK_LABELS:
        node_http = framework_summary.get(framework)
        if isinstance(node_http, dict) and node_http.get("module_count"):
            node_parts = [_count_phrase(int(node_http["module_count"]), "route module")]
            route_path_count = int(node_http.get("route_path_count") or 0)
            if route_path_count:
                node_parts.append(_count_phrase(route_path_count, "path"))
            summary = f"{label} has " + " spanning ".join(node_parts)
            route_methods = [
                str(value) for value in node_http.get("route_methods") or [] if value
            ]
            if route_methods:
                summary += f" with verbs {human_list(route_methods)}"
            route_parts.append(summary)
    for framework, label in _PROVIDER_FRAMEWORK_LABELS:
        provider = framework_summary.get(framework)
        if isinstance(provider, dict) and provider.get("module_count"):
            provider_summary = (
                f"{label} SDK usage spans "
                f"{_count_phrase(int(provider['module_count']), 'module')}"
            )
            services = [str(value) for value in provider.get("services") or [] if value]
            if services:
                provider_summary += f" across services {human_list(services)}"
            client_symbols = [
                str(value) for value in provider.get("client_symbols") or [] if value
            ]
            if client_symbols:
                provider_summary += f" with clients {human_list(client_symbols)}"
            provider_parts.append(provider_summary)

    nextjs = framework_summary.get("nextjs")
    if isinstance(nextjs, dict) and nextjs.get("module_count"):
        next_parts: list[str] = []
        for key, label in (
            ("page_count", "page module"),
            ("layout_count", "layout module"),
            ("route_count", "route module"),
        ):
            count = int(nextjs.get(key) or 0)
            if count:
                next_parts.append(_count_phrase(count, label))
        metadata_count = int(nextjs.get("metadata_module_count") or 0)
        if metadata_count:
            next_parts.append(_count_phrase(metadata_count, "metadata provider"))
        route_verbs = [str(value) for value in nextjs.get("route_verbs") or [] if value]
        summary = (
            "Next.js has " + ", ".join(next_parts)
            if next_parts
            else "Next.js is present"
        )
        if route_verbs:
            summary += f" with verbs {human_list(route_verbs)}"
        app_parts.append(summary)

    react = framework_summary.get("react")
    if isinstance(react, dict) and react.get("module_count"):
        react_parts: list[str] = []
        for key, label in (
            ("client_boundary_count", "client module"),
            ("server_boundary_count", "server module"),
            ("shared_boundary_count", "shared module"),
            ("component_module_count", "component module"),
            ("hook_module_count", "hook-heavy module"),
        ):
            count = int(react.get(key) or 0)
            if count:
                react_parts.append(_count_phrase(count, label))
        if react_parts:
            app_parts.append("React has " + ", ".join(react_parts))
        else:
            app_parts.append("React is present")

    parts = route_parts + provider_parts + app_parts
    if not parts:
        return ""
    prefix = (
        "Framework and provider evidence shows "
        if provider_parts
        else "Framework evidence shows "
    )
    return prefix + " and ".join(parts) + "."


def build_framework_story_items(
    framework_summary: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Return bounded sample modules for story sections."""

    if not isinstance(framework_summary, dict):
        return []

    items: list[dict[str, Any]] = []
    for framework, _label in _PROVIDER_FRAMEWORK_LABELS:
        provider = framework_summary.get(framework)
        if isinstance(provider, dict):
            for row in provider.get("sample_modules") or []:
                if not isinstance(row, dict):
                    continue
                items.append({"framework": framework, **row})
    for framework, _label in _ROUTE_FRAMEWORK_LABELS:
        node_http = framework_summary.get(framework)
        if isinstance(node_http, dict):
            for row in node_http.get("sample_modules") or []:
                if not isinstance(row, dict):
                    continue
                items.append({"framework": framework, **row})
    nextjs = framework_summary.get("nextjs")
    if isinstance(nextjs, dict):
        for row in nextjs.get("sample_modules") or []:
            if not isinstance(row, dict):
                continue
            items.append({"framework": "nextjs", **row})
    react = framework_summary.get("react")
    if isinstance(react, dict):
        for row in react.get("sample_modules") or []:
            if not isinstance(row, dict):
                continue
            items.append({"framework": "react", **row})
    return items


def _count_phrase(count: int, singular: str) -> str:
    """Return a count phrase with simple pluralization."""

    suffix = "" if count == 1 else "s"
    return f"{count} {singular}{suffix}"


__all__ = ["build_framework_story_items", "summarize_framework_overview"]
