"""Unit tests for raw file-based relationship evidence extraction."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.relationships.execution import build_repository_checkouts
from platform_context_graph.relationships.file_evidence import (
    discover_checkout_file_evidence,
)


def test_discover_checkout_file_evidence_finds_terraform_repo_mapping(
    tmp_path: Path,
) -> None:
    """Terraform signals should produce dependency evidence for referenced repos."""

    service_repo = tmp_path / "api-node-search"
    infra_repo = tmp_path / "terraform-stack-search"
    service_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (infra_repo / "shared").mkdir(parents=True)
    (infra_repo / "shared" / "resources.tf").write_text(
        """
module "api_node_search" {
  source = "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"
  name = "api-node-search"
  app_repo = "api-node-search"
  config_path = "/configd/api-node-search/runtime"
}
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([infra_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("TERRAFORM_APP_REPO", "PROVISIONS_DEPENDENCY_FOR"),
        ("TERRAFORM_CONFIG_PATH", "PROVISIONS_DEPENDENCY_FOR"),
    ]
    assert {item.source_repo_id for item in evidence} == {checkouts[0].logical_repo_id}
    assert {item.target_repo_id for item in evidence} == {checkouts[1].logical_repo_id}


def test_discover_checkout_file_evidence_finds_helm_repo_mapping(
    tmp_path: Path,
) -> None:
    """Helm chart metadata should produce dependency evidence for repo names."""

    service_repo = tmp_path / "api-node-helm"
    chart_repo = tmp_path / "helm-stack-customer"
    service_repo.mkdir()
    chart_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (chart_repo / "Chart.yaml").write_text(
        """
apiVersion: v2
name: helm-stack-customer
dependencies:
  - name: api-node-helm
    repository: oci://ghcr.io/boatsgroup/charts
annotations:
  appRepo: api-node-helm
        """.strip() + "\n",
        encoding="utf-8",
    )
    (chart_repo / "values.yaml").write_text(
        """
service:
  upstreamRepo: api-node-helm
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([chart_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("HELM_CHART_REFERENCE", "DEPLOYS_FROM"),
        ("HELM_VALUES_REFERENCE", "DEPLOYS_FROM"),
    ]
    assert {item.source_repo_id for item in evidence} == {checkouts[1].logical_repo_id}
    assert {item.target_repo_id for item in evidence} == {checkouts[0].logical_repo_id}


def test_discover_checkout_file_evidence_finds_kustomize_repo_mapping(
    tmp_path: Path,
) -> None:
    """Kustomize overlays should emit dependency evidence for referenced repos."""

    service_repo = tmp_path / "api-node-kustomize"
    overlay_repo = tmp_path / "kustomize-customer"
    service_repo.mkdir()
    overlay_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (overlay_repo / "kustomization.yaml").write_text(
        """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - ../api-node-kustomize/base
helmCharts:
  - name: api-node-kustomize
    includeCRDs: false
images:
  - name: api-node-kustomize
    newTag: latest
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([overlay_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert {
        (item.evidence_kind, item.relationship_type) for item in evidence
    } == {
        ("KUSTOMIZE_HELM_CHART_REFERENCE", "DEPLOYS_FROM"),
        ("KUSTOMIZE_IMAGE_REFERENCE", "DEPLOYS_FROM"),
        ("KUSTOMIZE_RESOURCE_REFERENCE", "DEPLOYS_FROM"),
    }
    assert {item.source_repo_id for item in evidence} == {checkouts[1].logical_repo_id}
    assert {item.target_repo_id for item in evidence} == {checkouts[0].logical_repo_id}


def test_discover_checkout_file_evidence_ignores_kustomize_patch_paths(
    tmp_path: Path,
) -> None:
    """Kustomize patch file names alone should not create cross-repo mappings."""

    service_repo = tmp_path / "api-node-kustomize"
    overlay_repo = tmp_path / "kustomize-customer"
    service_repo.mkdir()
    overlay_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (overlay_repo / "kustomization.yaml").write_text(
        """
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
patches:
  - path: api-node-kustomize-patch.yaml
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([overlay_repo, service_repo])

    assert discover_checkout_file_evidence(checkouts) == []


def test_discover_checkout_file_evidence_finds_argocd_applicationset_discovery(
    tmp_path: Path,
) -> None:
    """ArgoCD ApplicationSets should emit config discovery relationships."""

    argocd_repo = tmp_path / "iac-eks-argocd"
    target_repo = tmp_path / "iac-eks-observability"
    (argocd_repo / "applicationsets").mkdir(parents=True)
    target_repo.mkdir()
    (target_repo / "README.md").write_text("observability repo\n", encoding="utf-8")
    (argocd_repo / "applicationsets" / "grafana.yaml").write_text(
        """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/iac-eks-observability
              revision: main
              files:
                - path: "argocd/grafana/overlays/*/config.yaml"
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([argocd_repo, target_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("ARGOCD_APPLICATIONSET_DISCOVERY", "DISCOVERS_CONFIG_IN")
    ]
    assert {item.source_repo_id for item in evidence} == {checkouts[0].logical_repo_id}
    assert {item.target_repo_id for item in evidence} == {checkouts[1].logical_repo_id}


def test_discover_checkout_file_evidence_finds_argocd_deploy_source(
    tmp_path: Path,
) -> None:
    """ArgoCD ApplicationSets should emit deploy-source relationships from config."""

    argocd_repo = tmp_path / "iac-eks-argocd"
    service_repo = tmp_path / "api-node-bw-home"
    target_repo = tmp_path / "helm-charts"
    (argocd_repo / "applicationsets").mkdir(parents=True)
    service_repo.mkdir()
    (target_repo / "argocd" / "api-node-bw-home" / "overlays" / "bg-qa").mkdir(
        parents=True
    )
    (argocd_repo / "applicationsets" / "api-node-bw-home.yaml").write_text(
        """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/helm-charts
              revision: main
              files:
                - path: "argocd/api-node-bw-home/overlays/*/config.yaml"
        """.strip() + "\n",
        encoding="utf-8",
    )
    (target_repo / "argocd" / "api-node-bw-home" / "overlays" / "bg-qa" / "config.yaml").write_text(
        """
git:
  repoURL: https://github.com/boatsgroup/helm-charts
  overlayPath: argocd/api-node-bw-home/overlays/bg-qa
helm:
  repoURL: boatsgroup.pe.jfrog.io
  chart: bg-helm/api-node-template
        """.strip() + "\n",
        encoding="utf-8",
    )

    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")

    checkouts = build_repository_checkouts([argocd_repo, target_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("ARGOCD_APPLICATIONSET_DISCOVERY", "DISCOVERS_CONFIG_IN"),
        ("ARGOCD_APPLICATIONSET_DEPLOY_SOURCE", "DEPLOYS_FROM"),
    ]
    discovery = next(
        item for item in evidence if item.relationship_type == "DISCOVERS_CONFIG_IN"
    )
    deploy = next(item for item in evidence if item.relationship_type == "DEPLOYS_FROM")

    assert discovery.source_repo_id == checkouts[0].logical_repo_id
    assert discovery.target_repo_id == checkouts[1].logical_repo_id
    assert deploy.source_repo_id == checkouts[2].logical_repo_id
    assert deploy.target_repo_id == checkouts[1].logical_repo_id


def test_discover_checkout_file_evidence_skips_argocd_deploy_source_without_repo_match(
    tmp_path: Path,
) -> None:
    """ArgoCD deploy-source evidence should skip add-ons that are not repos."""

    argocd_repo = tmp_path / "iac-eks-argocd"
    config_repo = tmp_path / "iac-eks-observability"
    (argocd_repo / "applicationsets").mkdir(parents=True)
    (config_repo / "argocd" / "grafana" / "overlays" / "ops-qa").mkdir(parents=True)
    (argocd_repo / "applicationsets" / "grafana.yaml").write_text(
        """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/iac-eks-observability
              revision: main
              files:
                - path: "argocd/grafana/overlays/*/config.yaml"
        """.strip() + "\n",
        encoding="utf-8",
    )
    (config_repo / "argocd" / "grafana" / "overlays" / "ops-qa" / "config.yaml").write_text(
        """
addon: grafana
environment: ops-qa
git:
  repoURL: https://github.com/boatsgroup/iac-eks-observability
  overlayPath: argocd/grafana/overlays/ops-qa
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([argocd_repo, config_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("ARGOCD_APPLICATIONSET_DISCOVERY", "DISCOVERS_CONFIG_IN")
    ]


def test_discover_checkout_file_evidence_skips_argocd_deploy_source_self_loop(
    tmp_path: Path,
) -> None:
    """ArgoCD deploy-source evidence should not emit repo self-loops."""

    argocd_repo = tmp_path / "iac-eks-argocd"
    target_repo = tmp_path / "helm-charts"
    (argocd_repo / "applicationsets").mkdir(parents=True)
    (target_repo / "argocd" / "api-node-bw-home" / "overlays" / "bg-qa").mkdir(
        parents=True
    )
    (argocd_repo / "applicationsets" / "api-node-bw-home.yaml").write_text(
        """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/helm-charts
              revision: main
              files:
                - path: "argocd/api-node-bw-home/overlays/*/config.yaml"
        """.strip() + "\n",
        encoding="utf-8",
    )
    (target_repo / "argocd" / "api-node-bw-home" / "overlays" / "bg-qa" / "config.yaml").write_text(
        """
git:
  repoURL: https://github.com/boatsgroup/iac-eks-argocd
  overlayPath: argocd/api-node-bw-home/overlays/bg-qa
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([argocd_repo, target_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [(item.evidence_kind, item.relationship_type) for item in evidence] == [
        ("ARGOCD_APPLICATIONSET_DISCOVERY", "DISCOVERS_CONFIG_IN")
    ]
    assert {item.source_repo_id for item in evidence} == {checkouts[0].logical_repo_id}
    assert {item.target_repo_id for item in evidence} == {checkouts[1].logical_repo_id}


def test_discover_checkout_file_evidence_ignores_unrelated_content(
    tmp_path: Path,
) -> None:
    """Unrelated infra content should not emit dependency evidence."""

    service_repo = tmp_path / "api-node-conversation"
    infra_repo = tmp_path / "terraform-module-karpenter"
    service_repo.mkdir()
    infra_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (infra_repo / "main.tf").write_text(
        """
module "karpenter" {
  source = "terraform-aws-modules/eks/aws//modules/karpenter"
}
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([infra_repo, service_repo])

    assert discover_checkout_file_evidence(checkouts) == []


def test_discover_checkout_file_evidence_emits_ecs_platform_evidence(
    tmp_path: Path,
) -> None:
    """Terraform ECS service configuration should emit platform runtime evidence."""

    service_repo = tmp_path / "api-node-boats"
    infra_repo = tmp_path / "terraform-stack-ecs"
    service_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (infra_repo / "shared").mkdir(parents=True)
    (infra_repo / "shared" / "resources.tf").write_text(
        """
resource "aws_ecs_cluster" "node10" {
  name = "node10"
}

module "api_node_boats" {
  source = "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"
  name = "api-node-boats"
  app_repo = "api-node-boats"
  cluster_name = "node10"
  service_discovery {
    cloudmap_namespace = "bg-qa"
  }
}
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([infra_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    pairs = {(item.evidence_kind, item.relationship_type) for item in evidence}
    assert ("TERRAFORM_ECS_CLUSTER", "PROVISIONS_PLATFORM") in pairs
    assert ("TERRAFORM_ECS_SERVICE", "RUNS_ON") in pairs
    assert ("TERRAFORM_APP_REPO", "PROVISIONS_DEPENDENCY_FOR") in pairs


def test_discover_checkout_file_evidence_emits_eks_platform_evidence(
    tmp_path: Path,
) -> None:
    """Terraform EKS cluster configuration should emit platform provisioning evidence."""

    infra_repo = tmp_path / "terraform-stack-eks"
    service_repo = tmp_path / "api-node-boats"
    infra_repo.mkdir()
    service_repo.mkdir()
    (service_repo / "README.md").write_text("service repo\n", encoding="utf-8")
    (infra_repo / "shared").mkdir(parents=True)
    (infra_repo / "shared" / "resources.tf").write_text(
        """
resource "aws_eks_cluster" "bg_qa" {
  name = "bg-qa"
}
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([infra_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    assert [
        (item.evidence_kind, item.relationship_type) for item in evidence
    ] == [("TERRAFORM_EKS_CLUSTER", "PROVISIONS_PLATFORM")]
    assert {item.source_repo_id for item in evidence} == {checkouts[0].logical_repo_id}


def test_discover_checkout_file_evidence_emits_argocd_platform_evidence(
    tmp_path: Path,
) -> None:
    """ArgoCD config discovery should also emit platform runtime evidence when explicit."""

    argocd_repo = tmp_path / "iac-eks-argocd"
    config_repo = tmp_path / "iac-eks-observability"
    service_repo = tmp_path / "helm-charts"
    (argocd_repo / "applicationsets").mkdir(parents=True)
    (config_repo / "argocd" / "grafana" / "overlays" / "ops-qa").mkdir(
        parents=True
    )
    service_repo.mkdir()
    (argocd_repo / "applicationsets" / "grafana.yaml").write_text(
        """
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - matrix:
        generators:
          - git:
              repoURL: https://github.com/boatsgroup/iac-eks-observability
              revision: main
              files:
                - path: "argocd/grafana/overlays/*/config.yaml"
        """.strip() + "\n",
        encoding="utf-8",
    )
    (config_repo / "argocd" / "grafana" / "overlays" / "ops-qa" / "config.yaml").write_text(
        """
name: api-node-bw-home
git:
  repoURL: https://github.com/boatsgroup/api-node-bw-home
  overlayPath: argocd/grafana/overlays/ops-qa
destinationClusterName: bg-qa
        """.strip() + "\n",
        encoding="utf-8",
    )

    checkouts = build_repository_checkouts([argocd_repo, config_repo, service_repo])

    evidence = discover_checkout_file_evidence(checkouts)

    pairs = {(item.evidence_kind, item.relationship_type) for item in evidence}
    assert ("ARGOCD_APPLICATIONSET_DISCOVERY", "DISCOVERS_CONFIG_IN") in pairs
    assert ("ARGOCD_DESTINATION_PLATFORM", "RUNS_ON") in pairs
