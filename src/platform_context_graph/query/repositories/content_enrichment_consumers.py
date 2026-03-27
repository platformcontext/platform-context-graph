"""Read-side consumer summaries derived from indexed content search."""

from __future__ import annotations

from typing import Any, Callable

from ...query import content as content_queries

_MAX_CONSUMER_REPOSITORIES = 12
_MAX_SAMPLE_PATHS = 3
_MAX_MATCHED_VALUES = 3


def extract_consumer_repositories(
    database: Any,
    *,
    repository: dict[str, Any],
    hostnames: list[dict[str, Any]],
    deployment_artifacts: dict[str, Any],
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    resolve_related_repo: Callable[[str], dict[str, Any] | None],
) -> list[dict[str, Any]]:
    """Return consumer repositories that reference this repo without deploying it."""

    repo_name = str(repository.get("name") or "").strip()
    repo_id = str(repository.get("id") or "").strip()
    if not repo_name:
        return []

    excluded_names = {
        repo_name,
        *{
            str(row.get("name") or "").strip()
            for row in [*deploys_from, *discovers_config_in, *provisioned_by]
            if isinstance(row, dict)
        },
    }
    patterns = _search_patterns(
        repo_name=repo_name,
        hostnames=hostnames,
        deployment_artifacts=deployment_artifacts,
    )
    aggregated: dict[str, dict[str, Any]] = {}
    for pattern_kind, pattern in patterns:
        result = content_queries.search_file_content(database, pattern=pattern)
        matches = result.get("matches") if isinstance(result, dict) else None
        if not isinstance(matches, list):
            continue
        for match in matches:
            repo_ref = resolve_related_repo(str(match.get("repo_id") or ""))
            if repo_ref is None:
                continue
            consumer_name = str(repo_ref.get("name") or "").strip()
            consumer_id = str(repo_ref.get("id") or "").strip()
            if not consumer_name or consumer_name in excluded_names:
                continue
            if repo_id and consumer_id == repo_id:
                continue
            _merge_consumer_match(
                aggregated=aggregated,
                repo_id=consumer_id or consumer_name,
                repo_name=consumer_name,
                evidence_kind=pattern_kind,
                matched_value=pattern,
                relative_path=str(match.get("relative_path") or "").strip(),
            )
    consumers = list(aggregated.values())
    consumers.sort(
        key=lambda row: (
            -len(row["evidence_kinds"]),
            -len(row["sample_paths"]),
            row["repository"],
        )
    )
    return consumers[:_MAX_CONSUMER_REPOSITORIES]


def _search_patterns(
    *,
    repo_name: str,
    hostnames: list[dict[str, Any]],
    deployment_artifacts: dict[str, Any],
) -> list[tuple[str, str]]:
    """Build ordered content-search patterns for consumer discovery."""

    patterns: list[tuple[str, str]] = [("repository_reference", repo_name)]
    seen = {repo_name}
    for row in hostnames:
        hostname = str(row.get("hostname") or "").strip()
        if not hostname or hostname in seen:
            continue
        seen.add(hostname)
        patterns.append(("hostname_reference", hostname))
    for row in deployment_artifacts.get("config_paths") or []:
        raw_path = str(row.get("path") or "").strip()
        normalized = raw_path.removesuffix("*").rstrip("/")
        if not normalized:
            continue
        search_value = normalized if normalized.endswith("/") else f"{normalized}/"
        if search_value in seen:
            continue
        seen.add(search_value)
        patterns.append(("config_path_reference", search_value))
    return patterns


def _merge_consumer_match(
    *,
    aggregated: dict[str, dict[str, Any]],
    repo_id: str,
    repo_name: str,
    evidence_kind: str,
    matched_value: str,
    relative_path: str,
) -> None:
    """Merge one content-search match into the aggregated consumer summary."""

    row = aggregated.setdefault(
        repo_id,
        {
            "repository": repo_name,
            "repo_id": repo_id,
            "evidence_kinds": [],
            "matched_values": [],
            "sample_paths": [],
        },
    )
    if evidence_kind and evidence_kind not in row["evidence_kinds"]:
        row["evidence_kinds"].append(evidence_kind)
    if matched_value and matched_value not in row["matched_values"]:
        row["matched_values"].append(matched_value)
        row["matched_values"] = row["matched_values"][:_MAX_MATCHED_VALUES]
    if relative_path and relative_path not in row["sample_paths"]:
        row["sample_paths"].append(relative_path)
        row["sample_paths"] = row["sample_paths"][:_MAX_SAMPLE_PATHS]
