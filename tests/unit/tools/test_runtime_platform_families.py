"""Tests for generic Terraform runtime-family helpers."""

from platform_context_graph.resolution.platform_families import (
    format_platform_kind_label,
    infer_runtime_family_kind_from_identifiers,
    infer_terraform_runtime_family_kind,
    lookup_runtime_family,
    matches_service_module_source,
    terraform_platform_evidence_kind,
)


def test_infer_terraform_runtime_family_kind_detects_ecs_from_cluster_resource() -> (
    None
):
    """Cluster resource types should resolve through the shared family registry."""

    content = 'resource "aws_ecs_cluster" "node10" { name = "node10" }\n'

    assert infer_terraform_runtime_family_kind(content) == "ecs"


def test_infer_terraform_runtime_family_kind_detects_eks_from_module_source() -> None:
    """Cluster module source patterns should also resolve through the registry."""

    content = """
module "eks" {
  source = "terraform-aws-modules/eks/aws"
}
""".strip()

    assert infer_terraform_runtime_family_kind(content) == "eks"


def test_matches_service_module_source_is_family_scoped() -> None:
    """Service module matching should be driven by the runtime family definition."""

    assert matches_service_module_source(
        'source = "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"',
        kind="ecs",
    )
    assert not matches_service_module_source(
        'source = "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"',
        kind="eks",
    )


def test_lookup_runtime_family_exposes_generic_family_metadata() -> None:
    """The registry should expose portable family metadata for contributors."""

    family = lookup_runtime_family("ecs")

    assert family is not None
    assert family.kind == "ecs"
    assert "aws_ecs_cluster" in family.cluster_resource_types
    assert "ecs-application/aws" in family.service_module_patterns


def test_terraform_platform_evidence_kind_is_family_driven() -> None:
    """Terraform evidence-kind names should derive from the shared registry."""

    assert terraform_platform_evidence_kind("ecs", scope="cluster") == (
        "TERRAFORM_ECS_CLUSTER"
    )
    assert terraform_platform_evidence_kind("eks", scope="service") == (
        "TERRAFORM_EKS_SERVICE"
    )


def test_format_platform_kind_label_prefers_registered_display_names() -> None:
    """Platform labels should stay consistent across runtime-aware summaries."""

    assert format_platform_kind_label("ecs") == "ECS"
    assert format_platform_kind_label("eks") == "EKS"
    assert format_platform_kind_label("kubernetes") == "Kubernetes"
    assert format_platform_kind_label("nomad") == "NOMAD"


def test_infer_runtime_family_kind_from_identifiers_uses_family_hints() -> None:
    """Repo-name and slug hints should use the same runtime-family registry."""

    assert infer_runtime_family_kind_from_identifiers(["iac-eks-argocd"]) == "eks"
    assert infer_runtime_family_kind_from_identifiers(["terraform-stack-ecs"]) == "ecs"
