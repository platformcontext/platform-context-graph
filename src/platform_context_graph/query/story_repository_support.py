"""Small support helpers for repository story shaping."""

from __future__ import annotations

from typing import Any


def dependency_label(row: Any) -> str:
    """Return a human-friendly dependency label from mixed response shapes."""

    if isinstance(row, str):
        return row.strip()
    if not isinstance(row, dict):
        return ""
    for key in ("name", "repository", "repo_name", "label", "id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return ""


def subject_from_repository(context: dict[str, Any]) -> dict[str, Any]:
    """Build a portable repository subject from repository context."""

    repository = context.get("repository") or {}
    return {
        "id": repository.get("id"),
        "type": "repository",
        "name": repository.get("name") or repository.get("repo_slug") or "repository",
        "repo_slug": repository.get("repo_slug"),
        "remote_url": repository.get("remote_url"),
        "has_remote": repository.get("has_remote"),
    }


def focused_deployment_story(lines: list[str]) -> list[str]:
    """Return the direct deployment story lines without dependency sprawl."""

    focused: list[str] = []
    for value in lines:
        line = str(value).strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("shared config"):
            continue
        if lower.startswith("consumer repositories"):
            continue
        if "consumer-only repository" in lower:
            continue
        focused.append(line)
    return focused
