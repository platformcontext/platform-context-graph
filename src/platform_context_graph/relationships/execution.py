"""Execution helpers for relationship checkout discovery and graph projection."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from ..observability import get_observability
from ..repository_identity import git_remote_for_path, repository_metadata
from ..utils.debug_log import emit_log_call, info_logger
from .entities import platform_from_entity_id, workload_subject_from_entity_id
from .file_evidence import discover_checkout_file_evidence
from .identity import canonical_checkout_id
from .models import RelationshipEvidenceFact, RepositoryCheckout, ResolvedRelationship

REPOSITORY_DEPENDENCY_SCOPE = "repo_dependencies"
_CROSS_REPO_RELATIONSHIP_TYPE_MAP = {
    "USES_MODULE": "PROVISIONS_DEPENDENCY_FOR",
}
_RELATIONSHIP_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")


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
    *,
    checkouts: Sequence[RepositoryCheckout] = (),
) -> list[RelationshipEvidenceFact]:
    """Discover repository dependency evidence from the current graph state."""

    evidence: list[RelationshipEvidenceFact] = []
    file_evidence: list[RelationshipEvidenceFact] = []
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
                        _CROSS_REPO_RELATIONSHIP_TYPE_MAP
                    ),
                },
            ):
                if _CROSS_REPO_RELATIONSHIP_TYPE_MAP:
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
                        relationship_types=list(_CROSS_REPO_RELATIONSHIP_TYPE_MAP),
                    ).data()
                else:
                    cross_repo_rows = []
            for row in cross_repo_rows:
                evidence_kind = str(row["evidence_kind"])
                evidence.append(
                    RelationshipEvidenceFact(
                        evidence_kind=evidence_kind,
                        relationship_type=_CROSS_REPO_RELATIONSHIP_TYPE_MAP[
                            evidence_kind
                        ],
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
            file_evidence = discover_checkout_file_evidence(checkouts)
            terraform_file_evidence_count = sum(
                1
                for item in file_evidence
                if item.evidence_kind.startswith("TERRAFORM_")
            )
            gitops_file_evidence_count = sum(
                1
                for item in file_evidence
                if item.evidence_kind.startswith("HELM_")
                or item.evidence_kind.startswith("KUSTOMIZE_")
                or item.evidence_kind.startswith("ARGOCD_")
            )
            platform_file_evidence_count = sum(
                1
                for item in file_evidence
                if item.relationship_type in {"RUNS_ON", "PROVISIONS_PLATFORM"}
            )
            evidence.extend(file_evidence)
            if discovery_span is not None:
                discovery_span.set_attribute(
                    "pcg.relationships.evidence_count",
                    len(evidence),
                )
                discovery_span.set_attribute(
                    "pcg.relationships.file_evidence_count",
                    len(file_evidence),
                )
                discovery_span.set_attribute(
                    "pcg.relationships.file_terraform_evidence_count",
                    terraform_file_evidence_count,
                )
                discovery_span.set_attribute(
                    "pcg.relationships.file_gitops_evidence_count",
                    gitops_file_evidence_count,
                )
                discovery_span.set_attribute(
                    "pcg.relationships.file_platform_evidence_count",
                    platform_file_evidence_count,
                )
                discovery_span.set_attribute(
                    "pcg.relationships.graph_evidence_count",
                    len(evidence) - len(file_evidence),
                )
        emit_log_call(
            info_logger,
            "Discovered repository dependency evidence",
            event_name="relationships.discover_evidence.completed",
            extra_keys={
                "graph_evidence_count": len(evidence) - len(file_evidence),
                "file_evidence_count": len(file_evidence),
                "file_terraform_evidence_count": terraform_file_evidence_count,
                "file_gitops_evidence_count": gitops_file_evidence_count,
                "file_platform_evidence_count": platform_file_evidence_count,
                "evidence_count": len(evidence),
            },
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
                    {
                        entity_id
                        for item in resolved
                        for entity_id in (
                            item.source_entity_id or item.source_repo_id,
                            item.target_entity_id or item.target_repo_id,
                        )
                        if entity_id and entity_id.startswith("repository:")
                    }
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
                    MATCH ()-[rel]->()
                    WHERE rel.evidence_source = 'resolver'
                    DELETE rel
                    """)
                if not resolved:
                    return
                platform_rows = _platform_projection_rows(resolved)
                if platform_rows:
                    tx.run(
                        """
                        UNWIND $rows AS row
                        MERGE (platform:Platform {id: row.entity_id})
                        SET platform.type = 'platform',
                            platform.name = row.name,
                            platform.kind = row.kind,
                            platform.provider = row.provider,
                            platform.environment = row.environment,
                            platform.region = row.region,
                            platform.locator = row.locator
                        """,
                        rows=platform_rows,
                    )
                workload_rows = _workload_subject_projection_rows(resolved)
                if workload_rows:
                    tx.run(
                        """
                        UNWIND $rows AS row
                        MERGE (workload:WorkloadSubject {id: row.entity_id})
                        SET workload.type = 'workload_subject',
                            workload.name = row.name,
                            workload.subject_type = row.subject_type,
                            workload.repository_id = row.repository_id,
                            workload.environment = row.environment,
                            workload.path = row.path
                        """,
                        rows=workload_rows,
                    )
                grouped_rows: dict[
                    tuple[str, str, str], list[dict[str, object]]
                ] = {}
                for item in resolved:
                    source_entity_id = item.source_entity_id or item.source_repo_id
                    target_entity_id = item.target_entity_id or item.target_repo_id
                    if source_entity_id is None or target_entity_id is None:
                        continue
                    group_key = (
                        _projection_label_for_entity_id(source_entity_id),
                        _projection_label_for_entity_id(target_entity_id),
                        item.relationship_type,
                    )
                    grouped_rows.setdefault(group_key, []).append(
                        {
                            "source_entity_id": source_entity_id,
                            "target_entity_id": target_entity_id,
                            "confidence": item.confidence,
                            "evidence_count": item.evidence_count,
                            "rationale": item.rationale,
                            "resolution_source": item.resolution_source,
                        }
                    )
                for (source_label, target_label, relationship_type), rows in sorted(
                    grouped_rows.items()
                ):
                    _validate_relationship_type(relationship_type)
                    tx.run(
                        f"""
                        UNWIND $rows AS row
                        MATCH (source:{source_label} {{id: row.source_entity_id}})
                        MATCH (target:{target_label} {{id: row.target_entity_id}})
                        MERGE (source)-[rel:{relationship_type}]->(target)
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
                        rows=rows,
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


def _platform_projection_rows(
    resolved: Sequence[ResolvedRelationship],
) -> list[dict[str, object]]:
    """Build stable graph-projection rows for referenced platform entities."""

    rows: dict[str, dict[str, object]] = {}
    for item in resolved:
        for entity_id in (item.source_entity_id, item.target_entity_id):
            if entity_id is None or not entity_id.startswith("platform:"):
                continue
            entity = platform_from_entity_id(entity_id)
            if entity is None or entity.entity_id in rows:
                continue
            rows[entity.entity_id] = {
                "entity_id": entity.entity_id,
                "name": entity.name or entity.entity_id,
                "kind": entity.kind,
                "provider": entity.provider,
                "environment": entity.environment,
                "region": entity.region,
                "locator": entity.locator,
            }
    return list(rows.values())


def _workload_subject_projection_rows(
    resolved: Sequence[ResolvedRelationship],
) -> list[dict[str, object]]:
    """Build stable graph-projection rows for referenced workload subjects."""

    rows: dict[str, dict[str, object]] = {}
    for item in resolved:
        for entity_id in (item.source_entity_id, item.target_entity_id):
            if entity_id is None or not entity_id.startswith("workload-subject:"):
                continue
            entity = workload_subject_from_entity_id(entity_id)
            if entity is None or entity.entity_id in rows:
                continue
            rows[entity.entity_id] = {
                "entity_id": entity.entity_id,
                "name": entity.name or entity.entity_id,
                "subject_type": entity.subject_type,
                "repository_id": entity.repository_id,
                "environment": entity.environment,
                "path": entity.path,
            }
    return list(rows.values())


def _projection_label_for_entity_id(entity_id: str) -> str:
    """Return the graph label to use for one canonical entity id."""

    if entity_id.startswith("repository:"):
        return "Repository"
    if entity_id.startswith("platform:"):
        return "Platform"
    if entity_id.startswith("workload-subject:"):
        return "WorkloadSubject"
    raise ValueError(f"unsupported canonical entity id for projection: {entity_id}")


def _validate_relationship_type(relationship_type: str) -> None:
    """Ensure dynamic graph projection uses a safe relationship type token."""

    if not _RELATIONSHIP_TYPE_RE.fullmatch(relationship_type):
        raise ValueError(
            f"invalid relationship type for projection: {relationship_type}"
        )
