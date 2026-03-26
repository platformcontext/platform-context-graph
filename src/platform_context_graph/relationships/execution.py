"""Execution helpers for relationship checkout discovery and graph projection."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable, Sequence

from ..observability import get_observability
from ..repository_identity import git_remote_for_path, repository_metadata
from .identity import canonical_checkout_id
from .models import RelationshipEvidenceFact, RepositoryCheckout, ResolvedRelationship

REPOSITORY_DEPENDENCY_SCOPE = "repo_dependencies"
_CROSS_REPO_RELATIONSHIP_TYPES = (
    "CONFIGURES",
    "DEPLOYS",
    "IMPLEMENTED_BY",
    "PATCHES",
    "ROUTES_TO",
    "RUNS_IMAGE",
    "SATISFIED_BY",
    "SELECTS",
    "SOURCES_FROM",
    "USES_IAM",
    "USES_MODULE",
)


def build_repository_checkouts(repo_paths: Iterable[Path]) -> list[RepositoryCheckout]:
    """Build checkout records for the repositories committed in one run."""

    records: list[RepositoryCheckout] = []
    for repo_path in repo_paths:
        repo_metadata = repository_metadata(
            name=repo_path.name,
            local_path=str(repo_path.resolve()),
            remote_url=git_remote_for_path(repo_path),
        )
        records.append(
            RepositoryCheckout(
                checkout_id=canonical_checkout_id(
                    logical_repo_id=repo_metadata["id"],
                    checkout_path=repo_metadata["local_path"],
                ),
                logical_repo_id=repo_metadata["id"],
                repo_name=repo_metadata["name"],
                repo_slug=repo_metadata.get("repo_slug"),
                remote_url=repo_metadata.get("remote_url"),
                checkout_path=repo_metadata.get("local_path"),
            )
        )
    return records


def discover_repository_dependency_evidence(
    driver: Any,
) -> list[RelationshipEvidenceFact]:
    """Discover repository dependency evidence from the current graph state."""

    evidence: list[RelationshipEvidenceFact] = []
    observability = get_observability()
    with observability.start_span(
        "pcg.relationships.discover_evidence",
        component=observability.component,
    ) as discovery_span:
        with driver.session() as session:
            with observability.start_span(
                "pcg.relationships.discover_evidence.workload",
                component=observability.component,
            ):
                workload_rows = session.run("""
                    MATCH (source:Workload)-[rel:DEPENDS_ON]->(target:Workload)
                    WHERE source.repo_id IS NOT NULL
                      AND target.repo_id IS NOT NULL
                      AND source.repo_id <> target.repo_id
                    RETURN source.repo_id AS source_repo_id,
                           target.repo_id AS target_repo_id,
                           coalesce(rel.confidence, 0.9) AS confidence,
                           coalesce(rel.reason, 'Workload dependency implies repository dependency') AS rationale,
                           source.id AS source_workload_id,
                           target.id AS target_workload_id
                    """).data()
            for row in workload_rows:
                evidence.append(
                    RelationshipEvidenceFact(
                        evidence_kind="WORKLOAD_DEPENDS_ON",
                        relationship_type="DEPENDS_ON",
                        source_repo_id=row["source_repo_id"],
                        target_repo_id=row["target_repo_id"],
                        confidence=float(row["confidence"]),
                        rationale=str(row["rationale"]),
                        details={
                            "source_workload_id": row.get("source_workload_id"),
                            "target_workload_id": row.get("target_workload_id"),
                        },
                    )
                )
            if discovery_span is not None:
                discovery_span.set_attribute(
                    "pcg.relationships.workload_evidence_count",
                    len(workload_rows),
                )

            with observability.start_span(
                "pcg.relationships.discover_evidence.cross_repo",
                component=observability.component,
                attributes={
                    "pcg.relationships.relationship_type_count": len(
                        _CROSS_REPO_RELATIONSHIP_TYPES
                    ),
                },
            ):
                cross_repo_rows = session.run(
                    """
                    MATCH (source_repo:Repository)-[:CONTAINS*]->(source_node)-[rel]->(target_node)<-[:CONTAINS*]-(target_repo:Repository)
                    WHERE source_repo.id <> target_repo.id
                      AND type(rel) IN $relationship_types
                    RETURN source_repo.id AS source_repo_id,
                           target_repo.id AS target_repo_id,
                           type(rel) AS evidence_kind,
                           coalesce(rel.confidence, 0.85) AS confidence,
                           coalesce(rel.reason, type(rel) + ' implies repository dependency') AS rationale,
                           labels(source_node) AS source_labels,
                           coalesce(source_node.id, source_node.name, '') AS source_identity,
                           labels(target_node) AS target_labels,
                           coalesce(target_node.id, target_node.name, '') AS target_identity
                    """,
                    relationship_types=list(_CROSS_REPO_RELATIONSHIP_TYPES),
                ).data()
            for row in cross_repo_rows:
                evidence.append(
                    RelationshipEvidenceFact(
                        evidence_kind=str(row["evidence_kind"]),
                        relationship_type="DEPENDS_ON",
                        source_repo_id=row["source_repo_id"],
                        target_repo_id=row["target_repo_id"],
                        confidence=float(row["confidence"]),
                        rationale=str(row["rationale"]),
                        details={
                            "source_labels": row.get("source_labels") or [],
                            "source_identity": row.get("source_identity"),
                            "target_labels": row.get("target_labels") or [],
                            "target_identity": row.get("target_identity"),
                        },
                    )
                )
            if discovery_span is not None:
                discovery_span.set_attribute(
                    "pcg.relationships.cross_repo_evidence_count",
                    len(cross_repo_rows),
                )
                discovery_span.set_attribute(
                    "pcg.relationships.evidence_count",
                    len(evidence),
                )
    return evidence


def project_resolved_relationships(
    *,
    db_manager: Any,
    generation_id: str,
    resolved: Sequence[ResolvedRelationship],
) -> None:
    """Project resolved repository dependencies back into the graph."""

    driver = db_manager.get_driver()
    observability = get_observability()
    with observability.start_span(
        "pcg.relationships.project",
        component=observability.component,
        attributes={
            "pcg.relationships.scope": REPOSITORY_DEPENDENCY_SCOPE,
            "pcg.relationships.generation_id": generation_id,
            "pcg.relationships.resolved_count": len(resolved),
        },
    ):
        with driver.session() as session:

            def _write_projection(tx: Any) -> None:
                """Replace resolver-managed graph edges inside one write transaction."""

                repo_ids = sorted(
                    {item.source_repo_id for item in resolved}
                    | {item.target_repo_id for item in resolved}
                )
                if repo_ids:
                    repo_rows = tx.run(
                        """
                        UNWIND $repo_ids AS repo_id
                        OPTIONAL MATCH (repo:Repository {id: repo_id})
                        RETURN repo_id, count(repo) AS repo_count
                        """,
                        repo_ids=repo_ids,
                    ).data()
                    missing_repo_ids = [
                        row["repo_id"]
                        for row in repo_rows
                        if int(row.get("repo_count", 0)) == 0
                    ]
                    if missing_repo_ids:
                        raise RuntimeError(
                            "Cannot project resolved repository relationships; "
                            "missing Repository nodes: "
                            + ", ".join(sorted(missing_repo_ids))
                        )
                tx.run("""
                    MATCH (:Repository)-[rel:DEPENDS_ON]->(:Repository)
                    WHERE rel.evidence_source = 'resolver'
                    DELETE rel
                    """)
                if not resolved:
                    return
                tx.run(
                    """
                    UNWIND $rows AS row
                    MATCH (source:Repository {id: row.source_repo_id})
                    MATCH (target:Repository {id: row.target_repo_id})
                    MERGE (source)-[rel:DEPENDS_ON]->(target)
                    SET rel.confidence = row.confidence,
                        rel.reason = row.rationale,
                        rel.evidence_source = 'resolver',
                        rel.evidence_generation_id = $generation_id,
                        rel.evidence_scope = $scope,
                        rel.evidence_count = row.evidence_count,
                        rel.resolution_source = row.resolution_source
                    """,
                    generation_id=generation_id,
                    scope=REPOSITORY_DEPENDENCY_SCOPE,
                    rows=[
                        {
                            "source_repo_id": item.source_repo_id,
                            "target_repo_id": item.target_repo_id,
                            "confidence": item.confidence,
                            "evidence_count": item.evidence_count,
                            "rationale": item.rationale,
                            "resolution_source": item.resolution_source,
                        }
                        for item in resolved
                    ],
                )

            execute_write = getattr(session, "execute_write", None)
            if callable(execute_write):
                execute_write(_write_projection)
                return
            write_transaction = getattr(session, "write_transaction", None)
            if callable(write_transaction):
                write_transaction(_write_projection)
                return
            _write_projection(session)
