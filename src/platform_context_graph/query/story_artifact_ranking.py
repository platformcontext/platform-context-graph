"""Artifact ranking helpers for support- and documentation-oriented stories."""

from __future__ import annotations

from typing import Any


def _artifact_rank(row: dict[str, Any]) -> int:
    """Return an explicit support-oriented rank for one artifact row."""

    relative_path = str(row.get("relative_path") or "").strip().lower()
    reason = str(row.get("reason") or "").strip().lower()

    if "/overlays/" in relative_path and "values" in relative_path:
        return 0
    if "/base/" in relative_path and "values" in relative_path:
        return 1
    if any(token in relative_path for token in ["xirsarole", "secret", "secrets"]):
        return 2
    if any(token in relative_path for token in ["dashboard", "grafana", "monitor"]):
        return 3
    if any(token in relative_path for token in ["openapi", "swagger"]):
        return 4
    if any(token in relative_path for token in ["catalog-specs", "specs/"]):
        return 5
    if any(
        token in relative_path for token in ["health", "probe", "_status", "_version"]
    ):
        return 6
    if any(
        token in relative_path
        for token in ["bootstrap", "main.", "server.", "app.", "entrypoint"]
    ) or any(token in reason for token in ["bootstrap", "main", "entrypoint"]):
        return 7
    if any(
        token in relative_path
        for token in ["runbook", "oncall", "support", "troubleshooting"]
    ):
        return 8
    if relative_path == "readme.md" or relative_path.startswith("docs/"):
        return 9
    return 10


def _artifact_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    """Return a stable sort key for one artifact row."""

    return (
        _artifact_rank(row),
        str(row.get("relative_path") or ""),
        str(row.get("repo_id") or ""),
    )


def _dedupe_artifacts(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return artifacts deduped by repo and relative path."""

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in artifacts:
        repo_id = str(row.get("repo_id") or "").strip()
        relative_path = str(row.get("relative_path") or "").strip()
        if not relative_path:
            continue
        key = (repo_id, relative_path)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _append_api_surface_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    api_surface: dict[str, Any],
) -> None:
    """Append API-spec and endpoint-backed artifacts."""

    for row in api_surface.get("spec_files") or []:
        if not isinstance(row, dict):
            continue
        relative_path = str(row.get("relative_path") or "").strip()
        if not relative_path:
            continue
        artifacts.append(
            {
                "repo_id": None,
                "relative_path": relative_path,
                "source_backend": "graph-context",
                "reason": row.get("discovered_from") or "api_spec",
            }
        )

    for row in api_surface.get("endpoints") or []:
        if not isinstance(row, dict):
            continue
        relative_path = str(row.get("relative_path") or "").strip()
        if not relative_path:
            continue
        artifacts.append(
            {
                "repo_id": None,
                "relative_path": relative_path,
                "source_backend": "graph-context",
                "reason": row.get("path") or "api_endpoint",
            }
        )


def _append_gitops_artifacts(
    artifacts: list[dict[str, Any]],
    *,
    gitops_overview: dict[str, Any] | None,
) -> None:
    """Append GitOps value, rendered, and supporting resource artifacts."""

    if not gitops_overview:
        return

    for row in gitops_overview.get("value_layers") or []:
        if not isinstance(row, dict):
            continue
        relative_path = str(row.get("relative_path") or "").strip()
        if not relative_path:
            continue
        artifacts.append(
            {
                "repo_id": None,
                "relative_path": relative_path,
                "source_backend": "graph-context",
                "reason": row.get("layer_kind"),
            }
        )

    for group_name in ("rendered_resources", "supporting_resources"):
        for row in gitops_overview.get(group_name) or []:
            if not isinstance(row, dict):
                continue
            relative_path = str(row.get("relative_path") or "").strip()
            if not relative_path:
                continue
            artifacts.append(
                {
                    "repo_id": None,
                    "relative_path": relative_path,
                    "source_backend": "graph-context",
                    "reason": row.get("kind") or row.get("source_family"),
                }
            )


def build_ranked_story_artifacts(
    *,
    documentation_evidence: dict[str, list[dict[str, Any]]],
    gitops_overview: dict[str, Any] | None,
    api_surface: dict[str, Any] | None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """Build one ranked, deduped artifact list for story and support consumers."""

    artifacts = [
        {
            "repo_id": row.get("repo_id"),
            "relative_path": row.get("relative_path"),
            "source_backend": row.get("source_backend"),
            "reason": row.get("summary") or row.get("snippet") or row.get("title"),
        }
        for row in [
            *documentation_evidence.get("file_content", []),
            *documentation_evidence.get("content_search", []),
        ]
        if isinstance(row, dict) and row.get("relative_path")
    ]
    _append_gitops_artifacts(artifacts, gitops_overview=gitops_overview)
    _append_api_surface_artifacts(artifacts, api_surface=api_surface or {})
    ranked = sorted(_dedupe_artifacts(artifacts), key=_artifact_sort_key)
    return ranked[:limit]
