"""Unit tests for investigation coverage and deployment-plane reporting."""

from __future__ import annotations

from platform_context_graph.query.investigation_coverage import (
    build_investigation_coverage_summary,
)


def test_build_coverage_summary_marks_multi_plane_when_controller_and_iac_exist() -> (
    None
):
    """Report multiple planes when controller and IAC evidence coexist."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=4,
        repositories_with_evidence_count=3,
        searched_evidence_families=[
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
            "network_routing",
        ],
        found_evidence_families=[
            "deployment_controller",
            "gitops_config",
            "iac_infrastructure",
        ],
        graph_completeness="partial",
        content_completeness="partial",
    )

    assert summary.deployment_mode == "multi_plane"
    assert [plane.name for plane in summary.deployment_planes] == [
        "gitops_controller_plane",
        "iac_infrastructure_plane",
    ]
    assert summary.missing_evidence_families == ["network_routing"]


def test_build_coverage_summary_marks_single_plane_when_only_gitops_exists() -> None:
    """Keep single-plane classification when only controller-backed evidence exists."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=2,
        repositories_with_evidence_count=2,
        searched_evidence_families=["deployment_controller", "gitops_config"],
        found_evidence_families=["deployment_controller", "gitops_config"],
        graph_completeness="complete",
        content_completeness="partial",
    )

    assert summary.deployment_mode == "single_plane"
    assert [plane.name for plane in summary.deployment_planes] == [
        "gitops_controller_plane"
    ]


def test_build_coverage_summary_marks_sparse_when_only_runtime_exists() -> None:
    """Report sparse mode when deployment evidence is missing but runtime exists."""

    summary = build_investigation_coverage_summary(
        repositories_considered_count=1,
        repositories_with_evidence_count=1,
        searched_evidence_families=["service_runtime", "network_routing"],
        found_evidence_families=["service_runtime"],
        graph_completeness="partial",
        content_completeness="unknown",
    )

    assert summary.deployment_mode == "sparse"
    assert summary.deployment_planes == []
    assert summary.missing_evidence_families == ["network_routing"]
