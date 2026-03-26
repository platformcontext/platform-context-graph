"""Unit tests for repository relationship resolution."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from platform_context_graph.relationships.models import (
    RelationshipAssertion,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolutionGeneration,
)
from platform_context_graph.relationships.resolver import (
    resolve_repository_relationships_for_committed_repositories,
    resolve_repository_relationships,
)


def test_resolve_repository_relationships_groups_evidence_into_one_edge() -> None:
    """Multiple evidence facts for one repo pair should aggregate deterministically."""

    evidence = [
        RelationshipEvidenceFact(
            evidence_kind="WORKLOAD_DEPENDS_ON",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.9,
            rationale="Runtime services list declares workload dependency",
            details={"source_workload": "workload:payments"},
        ),
        RelationshipEvidenceFact(
            evidence_kind="SOURCES_FROM",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.98,
            rationale="Argo source repository reference points at target repo",
            details={"source_node": "argocd:payments"},
        ),
    ]

    candidates, resolved = resolve_repository_relationships(evidence, assertions=[])

    assert len(candidates) == 1
    assert candidates[0].source_repo_id == "repository:r_payments"
    assert candidates[0].target_repo_id == "repository:r_auth"
    assert candidates[0].confidence == 0.98
    assert candidates[0].evidence_count == 2
    assert len(resolved) == 1
    assert resolved[0].resolution_source == "inferred"
    assert resolved[0].confidence == 0.98
    assert resolved[0].evidence_count == 2


def test_resolve_repository_relationships_rejection_blocks_inferred_edge() -> None:
    """Explicit rejections should prevent inference from becoming canonical."""

    evidence = [
        RelationshipEvidenceFact(
            evidence_kind="WORKLOAD_DEPENDS_ON",
            relationship_type="DEPENDS_ON",
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            confidence=0.9,
            rationale="Runtime services list declares workload dependency",
        )
    ]
    assertions = [
        RelationshipAssertion(
            source_repo_id="repository:r_payments",
            target_repo_id="repository:r_auth",
            relationship_type="DEPENDS_ON",
            decision="reject",
            reason="False positive for fixture repo",
            actor="tester",
        )
    ]

    candidates, resolved = resolve_repository_relationships(evidence, assertions)

    assert len(candidates) == 1
    assert resolved == []


def test_resolve_repository_relationships_assertion_creates_edge_without_evidence() -> (
    None
):
    """Explicit assertions should create canonical edges even without raw evidence."""

    assertions = [
        RelationshipAssertion(
            source_repo_id="repository:r_deployments",
            target_repo_id="repository:r_payments",
            relationship_type="DEPENDS_ON",
            decision="assert",
            reason="Deployment repo intentionally tracks service repo",
            actor="tester",
        )
    ]

    candidates, resolved = resolve_repository_relationships([], assertions)

    assert candidates == []
    assert len(resolved) == 1
    assert resolved[0].source_repo_id == "repository:r_deployments"
    assert resolved[0].target_repo_id == "repository:r_payments"
    assert resolved[0].confidence == 1.0
    assert resolved[0].resolution_source == "assertion"
    assert resolved[0].evidence_count == 0


def test_resolve_repository_relationships_for_committed_repositories_activates_after_projection(
    monkeypatch,
    tmp_path: Path,
) -> None:
    """A new generation should become active only after Neo4j projection succeeds."""

    repo_path = tmp_path / "payments-api"
    repo_path.mkdir()
    call_order: list[str] = []

    class FakeStore:
        enabled = True

        def list_relationship_assertions(self, *, relationship_type: str):
            call_order.append(f"assertions:{relationship_type}")
            return []

        def replace_generation(self, **_kwargs):
            call_order.append("replace_generation")
            return ResolutionGeneration(
                generation_id="generation_123",
                scope="repo_dependencies",
                run_id="run_123",
                status="pending",
            )

        def activate_generation(self, *, scope: str, generation_id: str) -> None:
            call_order.append(f"activate:{scope}:{generation_id}")

    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.get_relationship_store",
        lambda: FakeStore(),
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.build_repository_checkouts",
        lambda repo_paths: [
            RepositoryCheckout(
                checkout_id="checkout_123",
                logical_repo_id="repository:r_payments",
                repo_name=Path(next(iter(repo_paths))).name,
                checkout_path=str(repo_path),
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.discover_repository_dependency_evidence",
        lambda _driver: [
            RelationshipEvidenceFact(
                evidence_kind="WORKLOAD_DEPENDS_ON",
                relationship_type="DEPENDS_ON",
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_orders",
                confidence=0.9,
                rationale="Workload dependency implies repository dependency",
            )
        ],
    )
    monkeypatch.setattr(
        "platform_context_graph.relationships.resolver.project_resolved_relationships",
        lambda **_kwargs: call_order.append("project"),
    )

    stats = resolve_repository_relationships_for_committed_repositories(
        builder=SimpleNamespace(driver=object(), db_manager=object()),
        committed_repo_paths=[repo_path],
        run_id="run_123",
        info_logger_fn=MagicMock(),
    )

    assert stats == {
        "checkouts": 1,
        "evidence_facts": 1,
        "candidates": 1,
        "resolved_relationships": 1,
    }
    assert call_order == [
        "assertions:DEPENDS_ON",
        "replace_generation",
        "project",
        "activate:repo_dependencies:generation_123",
    ]
