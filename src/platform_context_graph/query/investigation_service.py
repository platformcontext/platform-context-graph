"""Query-layer orchestration for service investigations."""

from __future__ import annotations

import re
from typing import Any

from platform_context_graph.domain.investigation_responses import (
    InvestigationFinding,
    InvestigationResponse,
)
from platform_context_graph.mcp.tools.handlers.ecosystem_support import (
    trace_deployment_chain,
)

from . import content as content_queries
from . import context as context_queries
from . import entity_resolution as entity_resolution_queries
from . import repositories as repository_queries
from .investigation_coverage import build_investigation_coverage_summary
from .investigation_evidence_families import INVESTIGATION_EVIDENCE_FAMILIES
from .investigation_intent import (
    infer_investigation_intent,
    normalize_investigation_intent,
)
from .investigation_recommendations import (
    build_recommended_next_calls,
    build_recommended_next_steps,
)
from .investigation_repo_widening import widen_related_repositories

_EXTERNAL_REPO_RE = re.compile(r"\b[\w.-]+/([\w.-]+)\b")


def _primary_refs_from_resolution(
    resolve_response: dict[str, Any],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the primary workload ref and repository ref from entity resolution."""

    workload_ref = None
    repository_ref = None
    for match in resolve_response.get("matches", []):
        ref = match.get("ref") or {}
        if workload_ref is None and ref.get("type") == "workload":
            workload_ref = ref
        if repository_ref is None and ref.get("type") == "repository":
            repository_ref = ref
    return workload_ref, repository_ref


def _workflow_findings_for_primary_repo(
    database: Any, *, primary_repo_id: str | None, service_name: str
) -> list[dict[str, Any]]:
    """Return workflow findings derived from app-repo content search results."""

    if not primary_repo_id:
        return []
    search_response = content_queries.search_file_content(
        database,
        pattern=service_name,
        repo_ids=[primary_repo_id],
    )
    findings: list[dict[str, Any]] = []
    for match in search_response.get("matches", []):
        relative_path = str(match.get("relative_path") or "")
        if not relative_path.startswith(".github/workflows/"):
            continue
        snippet = str(match.get("snippet") or "")
        external_repositories = sorted(
            {repo_name for repo_name in _EXTERNAL_REPO_RE.findall(snippet)}
        )
        findings.append(
            {
                "relative_path": relative_path,
                "external_repositories": external_repositories,
            }
        )
    return findings


def _add_related_repo_details(
    database: Any, *, widened_repositories: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Attach canonical repo identifiers when the widened repo can be resolved."""

    detailed_repositories: list[dict[str, Any]] = []
    for repository in widened_repositories:
        repo_name = repository.get("repo_name")
        if not isinstance(repo_name, str) or not repo_name:
            continue
        repo_story = repository_queries.get_repository_story(
            database, repo_id=repo_name
        )
        subject = repo_story.get("subject") or {}
        repo_id = subject.get("id")
        detailed_repository = dict(repository)
        if isinstance(repo_id, str) and repo_id:
            detailed_repository["repo_id"] = repo_id
        detailed_repositories.append(detailed_repository)
    return detailed_repositories


def _evidence_families_found(
    *,
    service_story: dict[str, Any],
    deployment_trace: dict[str, Any],
    related_repositories: list[dict[str, Any]],
    workflow_findings: list[dict[str, Any]],
) -> list[str]:
    """Return a stable ordered list of found evidence families."""

    found_families: list[str] = []
    if service_story.get("subject"):
        found_families.append("service_runtime")
    if deployment_trace.get("argocd_applicationsets") or deployment_trace.get(
        "argocd_applications"
    ):
        found_families.extend(["deployment_controller", "gitops_config"])
    for repository in related_repositories:
        for family in repository.get("evidence_families", []):
            if family not in found_families:
                found_families.append(family)
    if workflow_findings and "ci_cd_pipeline" not in found_families:
        found_families.append("ci_cd_pipeline")
    return [
        family
        for family in INVESTIGATION_EVIDENCE_FAMILIES
        if family in set(found_families)
    ]


def investigate_service(
    database: Any,
    *,
    service_name: str,
    environment: str | None = None,
    intent: str | None = None,
    question: str | None = None,
) -> dict[str, Any]:
    """Investigate one service using coordinated PCG evidence retrieval."""

    requested_intent = normalize_investigation_intent(
        intent
    ) or infer_investigation_intent(question)
    if requested_intent == "overview" and question:
        requested_intent = infer_investigation_intent(question)

    resolve_response = entity_resolution_queries.resolve_entity(
        database,
        query=service_name,
        types=["workload", "repository"],
        kinds=["service"],
        exact=False,
        limit=10,
    )
    workload_ref, repository_ref = _primary_refs_from_resolution(resolve_response)
    workload_id = str((workload_ref or {}).get("id") or f"workload:{service_name}")
    primary_repo_id = (repository_ref or {}).get("id")
    primary_repo_name = str((repository_ref or {}).get("name") or service_name)

    service_story = context_queries.get_service_story(
        database,
        workload_id=workload_id,
        environment=environment,
    )
    primary_repo_story = (
        repository_queries.get_repository_story(database, repo_id=primary_repo_id)
        if isinstance(primary_repo_id, str) and primary_repo_id
        else {}
    )
    del primary_repo_story  # Reserved for later richer findings.
    primary_repo_context = (
        repository_queries.get_repository_context(database, repo_id=primary_repo_id)
        if isinstance(primary_repo_id, str) and primary_repo_id
        else {}
    )
    del primary_repo_context  # Reserved for later richer widening.
    deployment_trace = trace_deployment_chain(
        database,
        service_name,
        direct_only=True,
        include_related_module_usage=False,
    )
    workflow_findings = _workflow_findings_for_primary_repo(
        database,
        primary_repo_id=primary_repo_id if isinstance(primary_repo_id, str) else None,
        service_name=service_name,
    )
    widened_repositories = widen_related_repositories(
        service_name=service_name,
        primary_repo_name=primary_repo_name,
        deployment_trace=deployment_trace,
        workflow_findings=workflow_findings,
    )
    related_repositories = _add_related_repo_details(
        database,
        widened_repositories=widened_repositories,
    )
    found_evidence_families = _evidence_families_found(
        service_story=service_story,
        deployment_trace=deployment_trace,
        related_repositories=related_repositories,
        workflow_findings=workflow_findings,
    )

    searched_evidence_families = [
        "service_runtime",
        "deployment_controller",
        "gitops_config",
        "iac_infrastructure",
        "identity_and_iam",
        "ci_cd_pipeline",
    ]
    coverage_summary = build_investigation_coverage_summary(
        repositories_considered_count=1 + len(related_repositories),
        repositories_with_evidence_count=len(related_repositories),
        searched_evidence_families=searched_evidence_families,
        found_evidence_families=found_evidence_families,
        graph_completeness="partial",
        content_completeness="partial",
    )
    recommended_next_calls = build_recommended_next_calls(
        repositories_with_evidence=related_repositories
    )
    response = InvestigationResponse(
        summary=[
            f"Investigation intent: {requested_intent}.",
            f"Primary service: {service_name}.",
        ],
        repositories_considered=[
            {
                "repo_id": (
                    primary_repo_id if isinstance(primary_repo_id, str) else None
                ),
                "repo_name": primary_repo_name,
                "reason": "primary_service_repository",
                "evidence_families": ["service_runtime"],
            },
            *related_repositories,
        ],
        repositories_with_evidence=related_repositories,
        evidence_families_found=found_evidence_families,
        coverage_summary=coverage_summary,
        investigation_findings=[
            InvestigationFinding(
                title="Service investigation initialized",
                summary=(
                    "PCG combined service, deployment, workflow, and related "
                    "repository evidence for this service."
                ),
                evidence_families=found_evidence_families,
            )
        ],
        limitations=list(service_story.get("limitations") or []),
        recommended_next_steps=build_recommended_next_steps(
            recommended_next_calls=recommended_next_calls
        ),
        recommended_next_calls=recommended_next_calls,
    )
    return response.model_dump(mode="json")


__all__ = ["investigate_service"]
