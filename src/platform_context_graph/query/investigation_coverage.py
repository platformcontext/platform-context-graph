"""Coverage and deployment-plane helpers for service investigations."""

from __future__ import annotations

from platform_context_graph.domain.investigation_responses import (
    InvestigationCoverageState,
    InvestigationCoverageSummary,
    InvestigationDeploymentPlane,
)


def _deployment_planes_for_families(
    found_evidence_families: list[str],
) -> list[InvestigationDeploymentPlane]:
    """Return deployment planes implied by the found evidence families."""

    planes: list[InvestigationDeploymentPlane] = []
    found = set(found_evidence_families)
    if {"deployment_controller", "gitops_config"} & found:
        planes.append(
            InvestigationDeploymentPlane(
                name="gitops_controller_plane",
                evidence_families=[
                    family
                    for family in ("deployment_controller", "gitops_config")
                    if family in found
                ],
            )
        )
    if "iac_infrastructure" in found:
        planes.append(
            InvestigationDeploymentPlane(
                name="iac_infrastructure_plane",
                evidence_families=["iac_infrastructure"],
            )
        )
    return planes


def _deployment_mode_for_planes(
    *,
    deployment_planes: list[InvestigationDeploymentPlane],
    found_evidence_families: list[str],
) -> str:
    """Return the deployment-mode label for one evidence-family combination."""

    if len(deployment_planes) > 1:
        return "multi_plane"
    if len(deployment_planes) == 1:
        return "single_plane"
    if found_evidence_families:
        return "sparse"
    return "none"


def build_investigation_coverage_summary(
    *,
    repositories_considered_count: int,
    repositories_with_evidence_count: int,
    searched_evidence_families: list[str],
    found_evidence_families: list[str],
    graph_completeness: InvestigationCoverageState,
    content_completeness: InvestigationCoverageState,
) -> InvestigationCoverageSummary:
    """Build one typed coverage summary for a service investigation."""

    found_family_set = set(found_evidence_families)
    missing_evidence_families = [
        family
        for family in searched_evidence_families
        if family not in found_family_set
    ]
    deployment_planes = _deployment_planes_for_families(found_evidence_families)

    return InvestigationCoverageSummary(
        searched_repository_count=repositories_considered_count,
        repositories_with_evidence_count=repositories_with_evidence_count,
        searched_evidence_families=searched_evidence_families,
        found_evidence_families=found_evidence_families,
        missing_evidence_families=missing_evidence_families,
        deployment_mode=_deployment_mode_for_planes(
            deployment_planes=deployment_planes,
            found_evidence_families=found_evidence_families,
        ),
        deployment_planes=deployment_planes,
        graph_completeness=graph_completeness,
        content_completeness=content_completeness,
    )


__all__ = ["build_investigation_coverage_summary"]
