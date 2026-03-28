"""Shared helpers for structured story responses."""

from __future__ import annotations

from typing import Any


def story_section(
    section_id: str,
    title: str,
    summary: str,
    *,
    items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return one structured story section."""

    return {
        "id": section_id,
        "title": title,
        "summary": summary,
        "items": list(items or []),
    }


def human_list(values: list[str], *, limit: int = 3) -> str:
    """Return a short human-readable list summary."""

    cleaned = [value for value in values if value]
    if not cleaned:
        return ""
    if len(cleaned) <= limit:
        return ", ".join(cleaned)
    shown = ", ".join(cleaned[:limit])
    return f"{shown}, and {len(cleaned) - limit} more"


def portable_story_value(value: Any) -> Any:
    """Strip server-local path details from story payloads."""

    if isinstance(value, list):
        return [portable_story_value(item) for item in value]
    if not isinstance(value, dict):
        return value

    entity_type = value.get("type")
    portable: dict[str, Any] = {}
    for key, item in value.items():
        if key in {"local_path", "repo_path", "repo_local_path"}:
            continue
        if key == "path" and entity_type == "repository":
            continue
        portable[key] = portable_story_value(item)
    return portable
