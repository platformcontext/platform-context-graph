"""Story-shaping helpers for high-level ecosystem deployment overviews."""

from typing import Any


def build_topology_story(
    *,
    hostnames: list[dict[str, Any]],
    api_surface: dict[str, Any],
    deployment_story: list[str],
    shared_config_paths: list[dict[str, Any]],
    consumer_repositories: list[dict[str, Any]],
) -> list[str]:
    """Build a compact internet-to-cloud-to-code narrative from derived facts."""

    lines: list[str] = []
    public_hostnames = [
        str(row.get("hostname") or "").strip()
        for row in hostnames
        if isinstance(row, dict) and str(row.get("hostname") or "").strip()
    ]
    if public_hostnames:
        lines.append(f"Public entrypoints: {', '.join(public_hostnames)}.")

    api_versions = [
        str(value).strip()
        for value in api_surface.get("api_versions") or []
        if str(value).strip()
    ]
    docs_routes = [
        str(value).strip()
        for value in api_surface.get("docs_routes") or []
        if str(value).strip()
    ]
    if api_versions or docs_routes:
        details: list[str] = []
        if api_versions:
            details.append(f"versions {', '.join(api_versions)}")
        if docs_routes:
            details.append(f"docs routes {', '.join(docs_routes)}")
        lines.append(f"API surface exposes {' and '.join(details)}.")

    lines.extend(deployment_story)
    shared_config_story = build_shared_config_story(shared_config_paths)
    if shared_config_story:
        lines.append(shared_config_story)
    consumer_story = build_consumer_story(consumer_repositories)
    if consumer_story:
        lines.append(consumer_story)

    return lines


def build_shared_config_story(rows: list[dict[str, Any]]) -> str:
    """Return one ranked, truncated shared-config story line."""

    grouped: dict[tuple[str, ...], list[str]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        path = str(row.get("path") or "").strip()
        source_repositories = tuple(
            str(value).strip()
            for value in row.get("source_repositories") or []
            if str(value).strip()
        )
        if not path or not source_repositories:
            continue
        grouped.setdefault(source_repositories, []).append(path)

    ranked_groups = sorted(
        grouped.items(),
        key=lambda item: (-len(item[0]), -len(item[1]), item[0]),
    )
    parts: list[str] = []
    shown_groups = 0
    for source_repositories, paths in ranked_groups[:2]:
        unique_paths = sorted(dict.fromkeys(paths))
        path_summary = limited_list(unique_paths, 2)
        repo_summary = limited_list(list(source_repositories), 3)
        parts.append(f"{repo_summary}: {path_summary}")
        shown_groups += 1
    if not parts:
        return ""
    extra_groups = len(ranked_groups) - shown_groups
    suffix = f"; and {extra_groups} more" if extra_groups > 0 else ""
    return f"Shared config families span {'; and '.join(parts)}{suffix}."


def build_consumer_story(rows: list[dict[str, Any]]) -> str:
    """Return one ranked consumer-only story line."""

    ranked = sorted(
        [
            row
            for row in rows
            if isinstance(row, dict) and str(row.get("repository") or "").strip()
        ],
        key=_consumer_rank_key,
    )
    if not ranked:
        return ""
    if len(ranked) == 1:
        row = ranked[0]
        repo = str(row.get("repository") or "").strip()
        evidence = _consumer_evidence_label(row)
        sample_path = str((row.get("sample_paths") or [""])[0]).strip()
        suffix = f" in {sample_path}" if evidence and sample_path else ""
        if evidence:
            return (
                f"Consumer-only repository {repo} references this service via "
                f"{evidence}{suffix}."
            )
        return f"Consumer-only repository {repo} references this service."
    top_row = ranked[0]
    top_repo = str(top_row.get("repository") or "").strip()
    top_evidence = _consumer_evidence_label(top_row)
    top_sample_path = str((top_row.get("sample_paths") or [""])[0]).strip()
    leading = f"Top consumer-only repository {top_repo} references this service"
    if top_evidence:
        leading += f" via {top_evidence}"
    if top_sample_path:
        leading += f" in {top_sample_path}"
    remaining = [row.get("repository") for row in ranked[1:]]
    if not remaining:
        return leading + "."
    return f"{leading}. Additional consumers: {limited_list(remaining, 2)}."


def limited_list(values: list[Any], limit: int) -> str:
    """Return an ordered, truncated comma-separated list."""

    ordered = [str(value).strip() for value in values if str(value).strip()]
    if len(ordered) <= limit:
        return ", ".join(ordered)
    shown = ", ".join(ordered[:limit])
    return f"{shown}, and {len(ordered) - limit} more"


def _consumer_rank_key(row: dict[str, Any]) -> tuple[int, int]:
    """Return a stable rank key for one consumer-only repository row."""

    evidence_kind = str((row.get("evidence_kinds") or [""])[0]).strip()
    evidence_rank = {
        "hostname_reference": 0,
        "config_path_reference": 1,
        "repository_reference": 2,
    }.get(evidence_kind, 3)
    has_sample_path = 0 if (row.get("sample_paths") or []) else 1
    return (evidence_rank, has_sample_path)


def _consumer_evidence_label(row: dict[str, Any]) -> str:
    """Return a human-readable evidence label for one consumer row."""

    kind = str((row.get("evidence_kinds") or [""])[0]).strip()
    return {
        "hostname_reference": "hostname references",
        "config_path_reference": "config path references",
        "repository_reference": "repository references",
    }.get(kind, kind.replace("_", " ").strip())


__all__ = [
    "build_consumer_story",
    "build_shared_config_story",
    "build_topology_story",
    "limited_list",
]
