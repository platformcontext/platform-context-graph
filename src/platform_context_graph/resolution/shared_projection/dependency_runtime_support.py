"""Neo4j write helpers for authoritative dependency projection workers."""

from __future__ import annotations

from typing import Any


def retract_repo_dependency_edges(
    session: Any,
    *,
    rows: list[dict[str, str]],
    evidence_source: str,
) -> None:
    """Delete targeted repository dependency edges before authoritative replay."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})-[rel:DEPENDS_ON]->(
            target_repo:Repository {id: row.target_repo_id}
        )
        WHERE rel.evidence_source = $evidence_source
        DELETE rel
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


def write_repo_dependency_edges(
    session: Any,
    *,
    rows: list[dict[str, object]],
    evidence_source: str,
) -> None:
    """Authoritatively upsert repository dependency edges."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})
        MATCH (target_repo:Repository {id: row.target_repo_id})
        MERGE (repo)-[rel:DEPENDS_ON]->(target_repo)
        SET rel.reason = 'Runtime services list declares repository dependency',
            rel.confidence = 0.98,
            rel.evidence_source = $evidence_source
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


def retract_workload_dependency_edges(
    session: Any,
    *,
    rows: list[dict[str, str]],
    evidence_source: str,
) -> None:
    """Delete targeted workload dependency edges before authoritative replay."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (source:Workload {id: row.workload_id})-[rel:DEPENDS_ON]->(
            target:Workload {id: row.target_workload_id}
        )
        WHERE rel.evidence_source = $evidence_source
        DELETE rel
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


def write_workload_dependency_edges(
    session: Any,
    *,
    rows: list[dict[str, object]],
    evidence_source: str,
) -> None:
    """Authoritatively upsert workload dependency edges."""

    if not rows:
        return
    session.run(
        """
        UNWIND $rows AS row
        MATCH (source:Workload {id: row.workload_id})
        MATCH (target:Workload {id: row.target_workload_id})
        MERGE (source)-[rel:DEPENDS_ON]->(target)
        SET rel.reason = 'Runtime services list declares workload dependency',
            rel.confidence = 0.98,
            rel.evidence_source = $evidence_source
        """,
        rows=rows,
        evidence_source=evidence_source,
    )


__all__ = [
    "retract_repo_dependency_edges",
    "retract_workload_dependency_edges",
    "write_repo_dependency_edges",
    "write_workload_dependency_edges",
]
