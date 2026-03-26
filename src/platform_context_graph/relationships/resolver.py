"""Evidence-backed repository dependency discovery and resolution."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from ..observability import get_observability
from ..repository_identity import git_remote_for_path, repository_metadata
from ..utils.debug_log import emit_log_call
from .identity import canonical_checkout_id
from .models import (
    RelationshipAssertion,
    RelationshipCandidate,
    RelationshipEvidenceFact,
    RepositoryCheckout,
    ResolvedRelationship,
)
from .state import get_relationship_store

REPOSITORY_DEPENDENCY_SCOPE = "repo_dependencies"
_INFERRED_CONFIDENCE_THRESHOLD = 0.75
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
    with get_observability().start_span("pcg.relationships.discover_evidence"):
        with driver.session() as session:
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
    return evidence


def resolve_repository_relationships(
    evidence_facts: Sequence[RelationshipEvidenceFact],
    assertions: Sequence[RelationshipAssertion],
    *,
    inferred_confidence_threshold: float = _INFERRED_CONFIDENCE_THRESHOLD,
) -> tuple[list[RelationshipCandidate], list[ResolvedRelationship]]:
    """Resolve raw evidence plus assertions into canonical repo dependencies."""

    grouped: dict[tuple[str, str, str], list[RelationshipEvidenceFact]] = defaultdict(
        list
    )
    for fact in evidence_facts:
        grouped[
            (fact.source_repo_id, fact.target_repo_id, fact.relationship_type)
        ].append(fact)

    candidates: list[RelationshipCandidate] = []
    for (source_repo_id, target_repo_id, relationship_type), facts in sorted(
        grouped.items()
    ):
        top_confidence = max(fact.confidence for fact in facts)
        rationale = "; ".join(
            value
            for value in dict.fromkeys(
                fact.rationale for fact in facts if fact.rationale
            )
        )
        candidates.append(
            RelationshipCandidate(
                source_repo_id=source_repo_id,
                target_repo_id=target_repo_id,
                relationship_type=relationship_type,
                confidence=top_confidence,
                evidence_count=len(facts),
                rationale=rationale,
                details={
                    "evidence_kinds": sorted({fact.evidence_kind for fact in facts}),
                    "evidence_preview": [
                        {
                            "kind": fact.evidence_kind,
                            "confidence": fact.confidence,
                            "details": fact.details,
                        }
                        for fact in facts[:5]
                    ],
                },
            )
        )

    rejections = {
        (item.source_repo_id, item.target_repo_id, item.relationship_type)
        for item in assertions
        if item.decision == "reject"
    }
    explicit_assertions = {
        (item.source_repo_id, item.target_repo_id, item.relationship_type): item
        for item in assertions
        if item.decision == "assert"
    }

    resolved: list[ResolvedRelationship] = []
    for candidate in candidates:
        key = (
            candidate.source_repo_id,
            candidate.target_repo_id,
            candidate.relationship_type,
        )
        if key in rejections or candidate.confidence < inferred_confidence_threshold:
            continue
        resolved.append(
            ResolvedRelationship(
                source_repo_id=candidate.source_repo_id,
                target_repo_id=candidate.target_repo_id,
                relationship_type=candidate.relationship_type,
                confidence=candidate.confidence,
                evidence_count=candidate.evidence_count,
                rationale=candidate.rationale,
                resolution_source="inferred",
                details=dict(candidate.details),
            )
        )

    existing_keys = {
        (item.source_repo_id, item.target_repo_id, item.relationship_type)
        for item in resolved
    }
    for key, assertion in sorted(explicit_assertions.items()):
        if key in rejections:
            continue
        if key in existing_keys:
            resolved = [
                (
                    item
                    if (
                        item.source_repo_id,
                        item.target_repo_id,
                        item.relationship_type,
                    )
                    != key
                    else ResolvedRelationship(
                        source_repo_id=assertion.source_repo_id,
                        target_repo_id=assertion.target_repo_id,
                        relationship_type=assertion.relationship_type,
                        confidence=1.0,
                        evidence_count=item.evidence_count,
                        rationale=assertion.reason,
                        resolution_source="assertion",
                        details={**item.details, "actor": assertion.actor},
                    )
                )
                for item in resolved
            ]
            continue
        resolved.append(
            ResolvedRelationship(
                source_repo_id=assertion.source_repo_id,
                target_repo_id=assertion.target_repo_id,
                relationship_type=assertion.relationship_type,
                confidence=1.0,
                evidence_count=0,
                rationale=assertion.reason,
                resolution_source="assertion",
                details={"actor": assertion.actor},
            )
        )

    resolved.sort(
        key=lambda item: (
            item.source_repo_id,
            item.target_repo_id,
            item.relationship_type,
        )
    )
    return candidates, resolved


def project_resolved_relationships(
    *,
    db_manager: Any,
    generation_id: str,
    resolved: Sequence[ResolvedRelationship],
) -> None:
    """Project resolved repository dependencies back into the graph."""

    driver = db_manager.get_driver()
    with get_observability().start_span(
        "pcg.relationships.project",
        attributes={
            "pcg.relationships.scope": REPOSITORY_DEPENDENCY_SCOPE,
            "pcg.relationships.resolved_count": len(resolved),
        },
    ):
        with driver.session() as session:

            def _write_projection(tx: Any) -> None:
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


def resolve_repository_relationships_for_committed_repositories(
    *,
    builder: Any,
    committed_repo_paths: Sequence[Path],
    run_id: str | None,
    info_logger_fn: Any,
) -> dict[str, int]:
    """Discover, resolve, persist, and project repo dependencies after ingest."""

    store = get_relationship_store()
    if store is None or not store.enabled:
        emit_log_call(
            info_logger_fn,
            "Relationship resolution skipped: Postgres relationship store is not configured",
            event_name="relationships.resolve.skipped",
            extra_keys={
                "scope": REPOSITORY_DEPENDENCY_SCOPE,
                "run_id": run_id or "adhoc",
            },
        )
        return {
            "checkouts": 0,
            "evidence_facts": 0,
            "candidates": 0,
            "resolved_relationships": 0,
        }

    with get_observability().start_span(
        "pcg.relationships.resolve_repository_dependencies",
        attributes={
            "pcg.relationships.run_id": run_id or "adhoc",
            "pcg.relationships.repo_count": len(committed_repo_paths),
        },
    ):
        emit_log_call(
            info_logger_fn,
            "Resolving repository dependencies from committed repositories",
            event_name="relationships.resolve.started",
            extra_keys={
                "scope": REPOSITORY_DEPENDENCY_SCOPE,
                "run_id": run_id or "adhoc",
                "repo_count": len(committed_repo_paths),
            },
        )
        checkouts = build_repository_checkouts(committed_repo_paths)
        evidence_facts = discover_repository_dependency_evidence(builder.driver)
        assertions = store.list_relationship_assertions(relationship_type="DEPENDS_ON")
        candidates, resolved = resolve_repository_relationships(
            evidence_facts,
            assertions,
        )
        generation = store.replace_generation(
            scope=REPOSITORY_DEPENDENCY_SCOPE,
            run_id=run_id,
            checkouts=checkouts,
            evidence_facts=evidence_facts,
            candidates=candidates,
            resolved=resolved,
        )
        project_resolved_relationships(
            db_manager=builder.db_manager,
            generation_id=generation.generation_id,
            resolved=resolved,
        )
        store.activate_generation(
            scope=REPOSITORY_DEPENDENCY_SCOPE,
            generation_id=generation.generation_id,
        )
        emit_log_call(
            info_logger_fn,
            "Repository dependency resolution complete",
            event_name="relationships.resolve.completed",
            extra_keys={
                "scope": REPOSITORY_DEPENDENCY_SCOPE,
                "run_id": run_id or "adhoc",
                "generation_id": generation.generation_id,
                "checkout_count": len(checkouts),
                "evidence_count": len(evidence_facts),
                "candidate_count": len(candidates),
                "resolved_count": len(resolved),
            },
        )
        return {
            "checkouts": len(checkouts),
            "evidence_facts": len(evidence_facts),
            "candidates": len(candidates),
            "resolved_relationships": len(resolved),
        }
