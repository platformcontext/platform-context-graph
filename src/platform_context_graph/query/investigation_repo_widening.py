"""Helpers that widen service investigations into related repositories."""

from __future__ import annotations

from typing import Any


def _repo_name_from_reference(value: str | None) -> str | None:
    """Extract a repository name from a URL, slug, or plain repo reference."""

    if not value:
        return None
    normalized = str(value).strip().rstrip("/")
    if not normalized:
        return None
    if normalized.endswith(".git"):
        normalized = normalized[:-4]
    if "/" not in normalized:
        return normalized
    return normalized.rsplit("/", maxsplit=1)[-1]


def _append_candidate(
    candidates: list[dict[str, Any]],
    seen_repo_names: set[str],
    *,
    repo_name: str | None,
    reason: str,
    evidence_families: list[str],
) -> None:
    """Add one unique widened repository candidate."""

    normalized_repo_name = _repo_name_from_reference(repo_name)
    if not normalized_repo_name or normalized_repo_name in seen_repo_names:
        return
    seen_repo_names.add(normalized_repo_name)
    candidates.append(
        {
            "repo_id": None,
            "repo_name": normalized_repo_name,
            "reason": reason,
            "evidence_families": evidence_families,
        }
    )


def widen_related_repositories(
    *,
    service_name: str,
    primary_repo_name: str | None,
    deployment_trace: dict[str, Any] | None = None,
    repository_findings: list[dict[str, Any]] | None = None,
    workflow_findings: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return widened related repositories justified by existing evidence."""

    del service_name  # Used by future heuristics once real evidence is wired in.

    candidates: list[dict[str, Any]] = []
    seen_repo_names: set[str] = {name for name in [primary_repo_name] if name}

    for applicationset in (deployment_trace or {}).get("argocd_applicationsets", []):
        for source_repo in applicationset.get("source_repos", []):
            _append_candidate(
                candidates,
                seen_repo_names,
                repo_name=source_repo,
                reason="argocd_source_repo",
                evidence_families=["deployment_controller", "gitops_config"],
            )

    for finding in repository_findings or []:
        oidc_subjects = [str(item) for item in finding.get("oidc_subjects", [])]
        if oidc_subjects:
            _append_candidate(
                candidates,
                seen_repo_names,
                repo_name=finding.get("repo_name"),
                reason="oidc_role_subject",
                evidence_families=["iac_infrastructure", "identity_and_iam"],
            )

    for finding in workflow_findings or []:
        for external_repo in finding.get("external_repositories", []):
            _append_candidate(
                candidates,
                seen_repo_names,
                repo_name=external_repo,
                reason="workflow_external_repo",
                evidence_families=["ci_cd_pipeline", "gitops_config"],
            )

    return candidates


__all__ = ["widen_related_repositories"]
