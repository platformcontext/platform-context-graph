"""Unit tests for the PostgreSQL relationship store."""

from __future__ import annotations

from contextlib import contextmanager
from unittest.mock import MagicMock

from platform_context_graph.relationships.models import (
    Platform,
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    ResolvedRelationship,
)
from platform_context_graph.relationships.postgres import (
    PostgresRelationshipStore,
    entity_or_repo_identity,
)


def test_replace_generation_persists_relationship_entities(monkeypatch) -> None:
    """Generation replacement should persist entity registry rows and entity ids."""

    store = PostgresRelationshipStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    generation = store.replace_generation(
        scope="repo_dependencies",
        run_id="run-123",
        checkouts=[],
        entities=[
            Platform(
                entity_id="platform:ecs:aws:cluster/node10:prod:us-east-1",
                kind="ecs",
                provider="aws",
                name="node10",
                environment="prod",
                region="us-east-1",
                locator="cluster/node10",
            )
        ],
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="WORKLOAD_DEPENDS_ON",
                relationship_type="DEPENDS_ON",
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_auth",
                source_entity_id="repository:r_payments",
                target_entity_id="repository:r_auth",
                confidence=0.9,
                rationale="Runtime dependency",
            )
        ],
        candidates=[
            RelationshipCandidate(
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_auth",
                source_entity_id="repository:r_payments",
                target_entity_id="repository:r_auth",
                relationship_type="DEPENDS_ON",
                confidence=0.9,
                evidence_count=1,
                rationale="Runtime dependency",
            )
        ],
        resolved=[
            ResolvedRelationship(
                source_repo_id="repository:r_payments",
                target_repo_id="repository:r_auth",
                source_entity_id="repository:r_payments",
                target_entity_id="repository:r_auth",
                relationship_type="DEPENDS_ON",
                confidence=0.9,
                evidence_count=1,
                rationale="Runtime dependency",
                resolution_source="inferred",
            )
        ],
    )

    assert generation.generation_id.startswith("generation_")

    entity_insert, entity_rows = cursor.executemany.call_args_list[0].args
    assert "INSERT INTO relationship_entities" in entity_insert
    assert entity_rows[0]["entity_id"] == "platform:ecs:aws:cluster/node10:prod:us-east-1"
    assert entity_rows[0]["entity_type"] == "Platform"
    assert entity_rows[0]["repository_id"] is None
    assert entity_rows[0]["subject_type"] is None
    assert entity_rows[0]["kind"] == "ecs"
    assert entity_rows[0]["provider"] == "aws"
    assert entity_rows[0]["name"] == "node10"
    assert entity_rows[0]["environment"] == "prod"
    assert entity_rows[0]["path"] is None
    assert entity_rows[0]["region"] == "us-east-1"
    assert entity_rows[0]["locator"] == "cluster/node10"
    assert entity_rows[0]["details"] == "{}"
    assert entity_rows[0]["created_at"] is not None
    assert entity_rows[0]["updated_at"] is not None

    evidence_insert, evidence_rows = cursor.executemany.call_args_list[1].args
    assert "source_entity_id" in evidence_insert
    assert evidence_rows[0]["source_entity_id"] == "repository:r_payments"
    assert evidence_rows[0]["target_entity_id"] == "repository:r_auth"


def test_replace_generation_persists_repo_to_platform_records(monkeypatch) -> None:
    """Generation replacement should allow mixed repo/platform relationship rows."""

    store = PostgresRelationshipStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    platform_id = "platform:ecs:aws:cluster/node10:prod:us-east-1"
    generation = store.replace_generation(
        scope="repo_dependencies",
        run_id="run-456",
        checkouts=[],
        entities=[
            Platform(
                entity_id=platform_id,
                kind="ecs",
                provider="aws",
                name="node10",
                environment="prod",
                region="us-east-1",
                locator="cluster/node10",
            )
        ],
        evidence_facts=[
            RelationshipEvidenceFact(
                evidence_kind="TERRAFORM_ECS_SERVICE",
                relationship_type="RUNS_ON",
                source_repo_id="repository:r_api",
                target_repo_id=None,
                source_entity_id="repository:r_api",
                target_entity_id=platform_id,
                confidence=0.95,
                rationale="Service module binds the repo to the ECS cluster.",
            )
        ],
        candidates=[
            RelationshipCandidate(
                source_repo_id="repository:r_api",
                target_repo_id=None,
                source_entity_id="repository:r_api",
                target_entity_id=platform_id,
                relationship_type="RUNS_ON",
                confidence=0.95,
                evidence_count=1,
                rationale="Service module binds the repo to the ECS cluster.",
            )
        ],
        resolved=[
            ResolvedRelationship(
                source_repo_id="repository:r_api",
                target_repo_id=None,
                source_entity_id="repository:r_api",
                target_entity_id=platform_id,
                relationship_type="RUNS_ON",
                confidence=0.95,
                evidence_count=1,
                rationale="Service runs on the resolved ECS platform.",
                resolution_source="inferred",
            )
        ],
    )

    assert generation.generation_id.startswith("generation_")

    evidence_insert, evidence_rows = cursor.executemany.call_args_list[1].args
    assert "INSERT INTO relationship_evidence_facts" in evidence_insert
    assert evidence_rows[0]["source_repo_id"] == "repository:r_api"
    assert evidence_rows[0]["target_repo_id"] is None
    assert evidence_rows[0]["source_entity_id"] == "repository:r_api"
    assert evidence_rows[0]["target_entity_id"] == platform_id

    candidate_insert, candidate_rows = cursor.executemany.call_args_list[2].args
    assert "INSERT INTO relationship_candidates" in candidate_insert
    assert candidate_rows[0]["source_repo_id"] == "repository:r_api"
    assert candidate_rows[0]["target_repo_id"] is None
    assert candidate_rows[0]["source_entity_id"] == "repository:r_api"
    assert candidate_rows[0]["target_entity_id"] == platform_id

    resolved_insert, resolved_rows = cursor.executemany.call_args_list[3].args
    assert "INSERT INTO resolved_relationships" in resolved_insert
    assert resolved_rows[0]["source_repo_id"] == "repository:r_api"
    assert resolved_rows[0]["target_repo_id"] is None
    assert resolved_rows[0]["source_entity_id"] == "repository:r_api"
    assert resolved_rows[0]["target_entity_id"] == platform_id


def test_existing_repo_backed_generation_remains_readable_until_entity_cutover(
    monkeypatch,
) -> None:
    """Resolved rows should stay readable while entity backfill is incomplete."""

    store = PostgresRelationshipStore("postgresql://example")
    cursor = MagicMock()
    cursor.fetchall.return_value = [
        {
            "source_repo_id": "repository:r_payments",
            "target_repo_id": "repository:r_auth",
            "source_entity_id": None,
            "target_entity_id": None,
            "relationship_type": "DEPENDS_ON",
            "confidence": 0.9,
            "evidence_count": 1,
            "rationale": "Runtime dependency",
            "resolution_source": "inferred",
            "details": {},
        }
    ]

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    resolved = store.list_resolved_relationships(scope="repo_dependencies")

    assert len(resolved) == 1
    assert resolved[0].source_repo_id == "repository:r_payments"
    assert resolved[0].target_repo_id == "repository:r_auth"
    assert resolved[0].source_entity_id == "repository:r_payments"
    assert resolved[0].target_entity_id == "repository:r_auth"


def test_backfill_populates_entity_ids_for_existing_repo_backed_rows() -> None:
    """Repo-backed rows should infer entity ids until explicit backfill lands."""

    row = {
        "source_repo_id": "repository:r_source",
        "target_repo_id": "repository:r_target",
        "source_entity_id": None,
        "target_entity_id": None,
    }

    assert entity_or_repo_identity(row, "source") == "repository:r_source"
    assert entity_or_repo_identity(row, "target") == "repository:r_target"


def test_upsert_relationship_assertion_persists_entity_ids(monkeypatch) -> None:
    """Assertion writes should persist explicit entity ids for future mixed-entity review."""

    store = PostgresRelationshipStore("postgresql://example")
    cursor = MagicMock()

    @contextmanager
    def _cursor():
        yield cursor

    monkeypatch.setattr(store, "_cursor", _cursor)

    store.upsert_relationship_assertion(
        RelationshipAssertion(
            source_repo_id="repository:r_argocd",
            target_repo_id="repository:r_helm",
            source_entity_id="workload-subject:repository:r_argocd:applicationset:external-search:bg-qa:argocd/external-search/overlays/bg-qa",
            target_entity_id="repository:r_helm",
            relationship_type="DEPLOYS_FROM",
            decision="assert",
            reason="ArgoCD application deploys manifests from the helm repo",
            actor="tester",
        )
    )

    sql, params = cursor.execute.call_args.args
    assert "source_entity_id" in sql
    assert "target_entity_id" in sql
    assert (
        params["source_entity_id"]
        == "workload-subject:repository:r_argocd:applicationset:external-search:bg-qa:argocd/external-search/overlays/bg-qa"
    )
    assert params["target_entity_id"] == "repository:r_helm"
