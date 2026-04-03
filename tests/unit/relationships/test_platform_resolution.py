"""Unit tests for mixed-entity platform relationship resolution."""

from __future__ import annotations

from platform_context_graph.relationships.models import (
    RelationshipAssertion,
    RelationshipEvidenceFact,
    ResolvedRelationship,
)
from platform_context_graph.relationships.platform_resolution import (
    resolve_entity_relationships,
)


def _resolved_keys(
    items: list[ResolvedRelationship],
) -> set[tuple[str | None, str | None, str]]:
    """Return the stable tuple form used by the mixed-entity assertions."""

    return {
        (item.source_entity_id, item.target_entity_id, item.relationship_type)
        for item in items
    }


def test_platform_chain_derives_depends_on_from_runs_on_and_provisions_platform() -> (
    None
):
    """RUNS_ON + PROVISIONS_PLATFORM should derive a repo-level compatibility edge."""

    _candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_CLUSTER",
                relationship_type="PROVISIONS_PLATFORM",
                source_repo_id="repository:r_terraform_stack_ecs",
                target_repo_id=None,
                source_entity_id="repository:r_terraform_stack_ecs",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.99,
                rationale="Terraform provisions the ECS cluster node10",
            ),
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_SERVICE",
                relationship_type="RUNS_ON",
                source_repo_id="repository:r_api_node_boats",
                target_repo_id=None,
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.97,
                rationale="Service deploy configuration binds the app to cluster node10",
            ),
        ],
        assertions=[],
    )

    assert _resolved_keys(resolved) >= {
        (
            "repository:r_terraform_stack_ecs",
            "platform:ecs:aws:cluster/node10:prod:us-east-1",
            "PROVISIONS_PLATFORM",
        ),
        (
            "repository:r_api_node_boats",
            "platform:ecs:aws:cluster/node10:prod:us-east-1",
            "RUNS_ON",
        ),
        (
            "repository:r_api_node_boats",
            "repository:r_terraform_stack_ecs",
            "DEPENDS_ON",
        ),
    }
    derived_edge = next(
        item for item in resolved if item.relationship_type == "DEPENDS_ON"
    )
    assert derived_edge.source_repo_id == "repository:r_api_node_boats"
    assert derived_edge.target_repo_id == "repository:r_terraform_stack_ecs"


def test_platform_chain_derives_depends_on_for_eks_platforms() -> None:
    """RUNS_ON + PROVISIONS_PLATFORM should also derive EKS compatibility edges."""

    _candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_EKS_CLUSTER",
                relationship_type="PROVISIONS_PLATFORM",
                source_repo_id="repository:r_terraform_stack_eks",
                target_repo_id=None,
                source_entity_id="repository:r_terraform_stack_eks",
                target_entity_id="platform:eks:aws:cluster/bg-qa:qa:us-east-1",
                confidence=0.99,
                rationale="Terraform provisions the EKS cluster bg-qa",
            ),
            RelationshipEvidenceFact(
                evidence_kind="ARGOCD_DESTINATION_PLATFORM",
                relationship_type="RUNS_ON",
                source_repo_id="repository:r_api_node_boats",
                target_repo_id=None,
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="platform:eks:aws:cluster/bg-qa:qa:us-east-1",
                confidence=0.98,
                rationale="ArgoCD targets the bg-qa EKS cluster",
            ),
        ],
        assertions=[],
    )

    assert _resolved_keys(resolved) >= {
        (
            "repository:r_terraform_stack_eks",
            "platform:eks:aws:cluster/bg-qa:qa:us-east-1",
            "PROVISIONS_PLATFORM",
        ),
        (
            "repository:r_api_node_boats",
            "platform:eks:aws:cluster/bg-qa:qa:us-east-1",
            "RUNS_ON",
        ),
        (
            "repository:r_api_node_boats",
            "repository:r_terraform_stack_eks",
            "DEPENDS_ON",
        ),
    }


def test_entity_resolver_does_not_emit_generic_dependency_to_platform_entities() -> (
    None
):
    """Generic compatibility edges should stay repo-to-repo, not repo-to-platform."""

    _candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="ARGOCD_DESTINATION_PLATFORM",
                relationship_type="RUNS_ON",
                source_repo_id="repository:r_api_node_boats",
                target_repo_id=None,
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="platform:eks:aws:cluster/bg-qa:qa:us-east-1",
                confidence=0.98,
                rationale="The service targets the bg-qa EKS cluster",
            )
        ],
        assertions=[],
    )

    assert _resolved_keys(resolved) == {
        (
            "repository:r_api_node_boats",
            "platform:eks:aws:cluster/bg-qa:qa:us-east-1",
            "RUNS_ON",
        )
    }


def test_entity_resolver_respects_generic_rejection_for_platform_chain_derivation() -> (
    None
):
    """Rejecting the compatibility edge should keep the typed platform edges intact."""

    _candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_CLUSTER",
                relationship_type="PROVISIONS_PLATFORM",
                source_repo_id="repository:r_terraform_stack_ecs",
                target_repo_id=None,
                source_entity_id="repository:r_terraform_stack_ecs",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.99,
                rationale="Terraform provisions the ECS cluster node10",
            ),
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_SERVICE",
                relationship_type="RUNS_ON",
                source_repo_id="repository:r_api_node_boats",
                target_repo_id=None,
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                confidence=0.97,
                rationale="Service deploy configuration binds the app to cluster node10",
            ),
        ],
        assertions=[
            RelationshipAssertion(
                source_repo_id="repository:r_api_node_boats",
                target_repo_id="repository:r_terraform_stack_ecs",
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="repository:r_terraform_stack_ecs",
                relationship_type="DEPENDS_ON",
                decision="reject",
                reason="Hide the compatibility edge in this scenario",
                actor="tester",
            )
        ],
    )

    assert _resolved_keys(resolved) == {
        (
            "repository:r_terraform_stack_ecs",
            "platform:ecs:aws:cluster/node10:prod:us-east-1",
            "PROVISIONS_PLATFORM",
        ),
        (
            "repository:r_api_node_boats",
            "platform:ecs:aws:cluster/node10:prod:us-east-1",
            "RUNS_ON",
        ),
    }


def test_entity_resolver_keeps_repo_ids_on_repo_backed_direct_compatibility_edges() -> (
    None
):
    """Repo-backed typed edges should retain repo ids on derived compatibility edges."""

    _candidates, resolved = resolve_entity_relationships(
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="ARGOCD_APPLICATIONSET_DEPLOY_SOURCE",
                relationship_type="DEPLOYS_FROM",
                source_repo_id="repository:r_api_node_boats",
                target_repo_id="repository:r_helm_charts",
                source_entity_id="repository:r_api_node_boats",
                target_entity_id="repository:r_helm_charts",
                confidence=0.99,
                rationale="The app deploys from the shared Helm repository",
            )
        ],
        assertions=[],
    )

    derived_edge = next(
        item for item in resolved if item.relationship_type == "DEPENDS_ON"
    )
    assert derived_edge.source_repo_id == "repository:r_api_node_boats"
    assert derived_edge.target_repo_id == "repository:r_helm_charts"
