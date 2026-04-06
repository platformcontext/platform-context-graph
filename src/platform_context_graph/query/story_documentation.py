"""Documentation orchestration helpers for story responses."""

from __future__ import annotations

import re
from typing import Any

from . import content as content_queries
from .repositories.indexed_file_discovery import discover_repo_files
from .story_artifact_ranking import build_ranked_story_artifacts
from .story_shared import human_list

_DOC_AUDIENCES = [
    "engineering",
    "service-owner",
    "platform-engineering",
    "support",
]
_DOCUMENTATION_PATH_RE = re.compile(
    r"(?i)(^README(?:\.[^.]+)?$|(^|/)(runbook|oncall|support|troubleshooting)\.md$|^docs/.+\.md$|(^|/)(Chart\.ya?ml|values(?:[-\w]*)?\.ya?ml|kustomization\.ya?ml|Dockerfile)$)"
)
_DOCUMENTATION_PATH_PATTERN = (
    r"(?i)(^README(?:\.[^.]+)?$|(^|/)(runbook|oncall|support|troubleshooting)\.md$"
    r"|^docs/.+\.md$|(^|/)(Chart\.ya?ml|values(?:[-\w]*)?\.ya?ml|kustomization\.ya?ml|Dockerfile)$)"
)


def _dedupe_repo_refs(repo_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return repository refs deduped by canonical ID."""

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for repo_ref in repo_refs:
        repo_id = str(repo_ref.get("id") or "").strip()
        if not repo_id or repo_id in seen:
            continue
        seen.add(repo_id)
        deduped.append(repo_ref)
    return deduped


def _candidate_paths(paths: list[str]) -> list[str]:
    """Return a ranked subset of documentation-shaped paths."""

    def sort_key(path: str) -> tuple[int, str]:
        """Rank likely human-facing docs ahead of generic config artifacts."""

        path_lower = path.lower()
        if path_lower == "readme.md":
            rank = 0
        elif "oncall" in path_lower or "runbook" in path_lower:
            rank = 1
        elif path_lower.startswith("docs/"):
            rank = 2
        else:
            rank = 3
        return (rank, path)

    filtered = [path for path in paths if _DOCUMENTATION_PATH_RE.search(path)]
    return sorted(filtered, key=sort_key)[:4]


def _summarize_document_text(content: str) -> tuple[str, str]:
    """Return a stable title and short summary from indexed content text."""

    heading = ""
    summary = ""
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not heading and line.startswith("#"):
            heading = line.lstrip("#").strip()
            continue
        if not heading:
            heading = line[:120]
            continue
        summary = line[:200]
        break
    return heading or "Indexed document", summary


def collect_documentation_evidence(
    database: Any,
    *,
    repo_refs: list[dict[str, Any]],
    subject_names: list[str],
) -> dict[str, list[dict[str, Any]]]:
    """Collect targeted Postgres-backed evidence for documentation answers."""

    deduped_repo_refs = _dedupe_repo_refs(repo_refs)
    if not deduped_repo_refs:
        return {
            "graph_context": [],
            "file_content": [],
            "entity_content": [],
            "content_search": [],
        }

    file_content_evidence: list[dict[str, Any]] = []
    search_evidence: list[dict[str, Any]] = []

    for repo_ref in deduped_repo_refs:
        repo_id = str(repo_ref.get("id") or "")
        candidate_paths = _candidate_paths(
            discover_repo_files(
                database,
                repo_id,
                pattern=_DOCUMENTATION_PATH_PATTERN,
            )
        )
        for relative_path in candidate_paths:
            read_result = content_queries.get_file_content(
                database,
                repo_id=repo_id,
                relative_path=relative_path,
            )
            if not read_result.get("available"):
                continue
            content = str(read_result.get("content") or "").strip()
            if not content:
                continue
            title, summary = _summarize_document_text(content)
            file_content_evidence.append(
                {
                    "repo_id": repo_id,
                    "relative_path": relative_path,
                    "source_backend": read_result.get("source_backend"),
                    "title": title,
                    "summary": summary,
                }
            )

    for subject_name in [name for name in subject_names if str(name).strip()]:
        search_result = content_queries.search_file_content(
            database,
            pattern=subject_name,
            repo_ids=[str(repo_ref.get("id")) for repo_ref in deduped_repo_refs],
        )
        for row in search_result.get("matches") or []:
            if not isinstance(row, dict):
                continue
            search_evidence.append(
                {
                    "repo_id": row.get("repo_id"),
                    "relative_path": row.get("relative_path"),
                    "source_backend": row.get("source_backend"),
                    "snippet": row.get("snippet"),
                }
            )
        if search_evidence:
            break

    return {
        "graph_context": [],
        "file_content": file_content_evidence,
        "entity_content": [],
        "content_search": search_evidence[:5],
    }


def build_graph_context_evidence(
    *,
    entrypoints: list[dict[str, Any]],
    delivery_paths: list[dict[str, Any]],
    deploys_from: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    api_surface: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build lightweight graph-first evidence markers for documentation answers."""

    evidence: list[dict[str, Any]] = []
    for row in entrypoints[:3]:
        hostname = str(row.get("hostname") or "").strip()
        if hostname:
            evidence.append({"kind": "entrypoint", "detail": hostname})
    for row in delivery_paths[:2]:
        controller = str(row.get("controller") or "").strip()
        delivery_mode = str(row.get("delivery_mode") or "").strip()
        detail = " ".join(
            value for value in [controller, delivery_mode] if value
        ).strip()
        if detail:
            evidence.append({"kind": "delivery_path", "detail": detail})
    for row in deploys_from[:2]:
        repo_name = str(row.get("name") or row.get("repo_slug") or "").strip()
        if repo_name:
            evidence.append({"kind": "source_repository", "detail": repo_name})
    for row in dependencies[:2]:
        dependency_name = str(row.get("name") or "").strip()
        if dependency_name:
            evidence.append({"kind": "dependency", "detail": dependency_name})
    endpoint_count = api_surface.get("endpoint_count")
    if endpoint_count:
        evidence.append(
            {"kind": "api_surface", "detail": f"{endpoint_count} endpoints"}
        )
    return evidence


def build_documentation_overview(
    *,
    subject_name: str,
    subject_type: str,
    repositories: list[dict[str, Any]],
    entrypoints: list[dict[str, Any]],
    dependencies: list[dict[str, Any]],
    api_surface: dict[str, Any] | None,
    code_overview: dict[str, Any] | None,
    gitops_overview: dict[str, Any] | None,
    documentation_evidence: dict[str, list[dict[str, Any]]],
    drilldowns: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a general-purpose documentation overview from story evidence."""

    if not any(documentation_evidence.values()) and not gitops_overview:
        return None

    repository_names = [
        str(row.get("name") or row.get("repo_slug") or "")
        for row in repositories
        if isinstance(row, dict)
    ]
    entrypoint_labels = [
        str(row.get("hostname") or row.get("path") or row.get("name") or "")
        for row in entrypoints
        if isinstance(row, dict)
    ]
    dependency_names = [
        str(row.get("name") or row.get("repository") or "")
        for row in dependencies
        if isinstance(row, dict)
    ]
    code_facts = code_overview or {}
    if subject_type == "repository":
        service_summary = f"{subject_name} is a repository story backed by {human_list(repository_names or [subject_name])}."
    else:
        service_summary = f"{subject_name} is a deployable service story backed by {human_list(repository_names or [subject_name])}."
    code_summary = (
        f"Code context includes {int(code_facts.get('functions') or 0)} functions, "
        f"{int(code_facts.get('classes') or 0)} classes, and "
        f"{int(code_facts.get('file_count') or 0)} discovered files."
        if code_overview is not None
        else "Code detail should be drilled into through repository and content reads."
    )
    deployment_summary_parts: list[str] = []
    if entrypoint_labels:
        deployment_summary_parts.append(
            f"Entry points include {human_list(entrypoint_labels, limit=5)}"
        )
    if gitops_overview:
        owner = gitops_overview.get("owner") or {}
        controllers = owner.get("delivery_controllers") or []
        if controllers:
            deployment_summary_parts.append(
                f"GitOps delivery uses {human_list([str(v) for v in controllers])}"
            )
    if dependency_names:
        deployment_summary_parts.append(
            f"Dependencies include {human_list(dependency_names)}"
        )
    deployment_summary = (
        ". ".join(deployment_summary_parts).strip() + "."
        if deployment_summary_parts
        else "Deployment detail is available through GitOps and context drilldowns."
    )

    key_artifacts = build_ranked_story_artifacts(
        documentation_evidence=documentation_evidence,
        gitops_overview=gitops_overview,
        api_surface=api_surface,
    )

    recommended_drilldowns = [
        {
            "tool": tool_name,
            "args": args,
        }
        for tool_name, args in drilldowns.items()
    ]

    limitations: list[str] = []
    if not documentation_evidence.get("file_content"):
        limitations.append("postgres_file_evidence_missing")
    if not documentation_evidence.get("content_search"):
        limitations.append("content_search_evidence_missing")

    return {
        "audiences": list(_DOC_AUDIENCES),
        "service_summary": service_summary,
        "code_summary": code_summary,
        "deployment_summary": deployment_summary,
        "key_artifacts": key_artifacts,
        "recommended_drilldowns": recommended_drilldowns,
        "documentation_evidence": documentation_evidence,
        "limitations": limitations,
    }


def summarize_documentation_overview(documentation_overview: dict[str, Any]) -> str:
    """Return a concise documentation section summary."""

    service_summary = str(documentation_overview.get("service_summary") or "").strip()
    key_artifacts = documentation_overview.get("key_artifacts") or []
    if key_artifacts:
        artifact_paths = [
            str(row.get("relative_path") or "")
            for row in key_artifacts
            if isinstance(row, dict) and str(row.get("relative_path") or "").strip()
        ]
        if artifact_paths:
            return (
                service_summary
                + " Key artifacts include "
                + human_list(artifact_paths, limit=4)
                + "."
            ).strip()
    return service_summary or "Documentation evidence is available for this story."
