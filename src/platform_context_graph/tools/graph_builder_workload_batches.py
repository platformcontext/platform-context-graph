"""Batched Neo4j projection helpers for workload finalization."""

from __future__ import annotations

from typing import Any, Iterable

_DEFAULT_BATCH_SIZE = 250


def _chunk_rows(
    rows: list[dict[str, object]], size: int = _DEFAULT_BATCH_SIZE
) -> Iterable[list[dict[str, object]]]:
    """Yield fixed-size chunks for Cypher `UNWIND` writes."""

    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def _run_batched_write(
    session: Any,
    query: str,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Execute one `UNWIND` write query in bounded chunks."""

    for chunk in _chunk_rows(rows):
        session.run(query, rows=chunk, evidence_source=evidence_source)


def retract_repo_dependency_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> None:
    """Delete workload-owned repository dependencies for targeted repos."""

    if not repo_ids:
        return
    session.run(
        """
        MATCH (source_repo:Repository)-[rel:DEPENDS_ON]->(:Repository)
        WHERE source_repo.id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        DELETE rel
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )


def retract_workload_dependency_rows(
    session: Any,
    repo_ids: list[str],
    *,
    active_workload_ids: list[str],
    evidence_source: str,
) -> None:
    """Delete targeted workload dependencies while preserving active targets."""

    if not repo_ids:
        return
    session.run(
        """
        MATCH (source:Workload)-[rel:DEPENDS_ON]->(:Workload)
        WHERE source.repo_id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        DELETE rel
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )
    session.run(
        """
        MATCH (target:Workload)
        WHERE target.repo_id IN $repo_ids
          AND target.evidence_source = $evidence_source
          AND NOT target.id IN $active_workload_ids
        MATCH (:Workload)-[rel:DEPENDS_ON]->(target)
        WHERE rel.evidence_source = $evidence_source
        DELETE rel
        """,
        active_workload_ids=active_workload_ids,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )


def retract_stale_workload_rows(
    session: Any,
    repo_ids: list[str],
    *,
    active_workload_ids: list[str],
    evidence_source: str,
) -> None:
    """Delete stale targeted workload nodes without touching active ones."""

    if not repo_ids:
        return
    session.run(
        """
        MATCH (repo:Repository)-[rel:DEFINES]->(w:Workload)
        WHERE repo.id IN $repo_ids
          AND rel.evidence_source = $evidence_source
          AND w.evidence_source = $evidence_source
          AND NOT w.id IN $active_workload_ids
        DELETE rel
        """,
        active_workload_ids=active_workload_ids,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )
    session.run(
        """
        MATCH (w:Workload)
        WHERE w.repo_id IN $repo_ids
          AND w.evidence_source = $evidence_source
          AND NOT w.id IN $active_workload_ids
          AND NOT (w)--()
        DELETE w
        """,
        active_workload_ids=active_workload_ids,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )


def retract_instance_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> None:
    """Delete targeted workload-instance state so it can be rebuilt cleanly."""

    if not repo_ids:
        return
    for relationship_type, target_label in (
        ("DEPLOYMENT_SOURCE", "Repository"),
        ("RUNS_ON", "Platform"),
        ("INSTANCE_OF", "Workload"),
    ):
        session.run(
            f"""
            MATCH (i:WorkloadInstance)
            WHERE i.repo_id IN $repo_ids
              AND i.evidence_source = $evidence_source
            MATCH (i)-[rel:{relationship_type}]->(:{target_label})
            WHERE rel.evidence_source = $evidence_source
            DELETE rel
            """,
            repo_ids=repo_ids,
            evidence_source=evidence_source,
        )
    session.run(
        """
        MATCH (i:WorkloadInstance)
        WHERE i.repo_id IN $repo_ids
          AND i.evidence_source = $evidence_source
          AND NOT (i)--()
        DELETE i
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )


def retract_infrastructure_platform_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> None:
    """Delete targeted infrastructure platform edges before re-materializing."""

    if not repo_ids:
        return
    session.run(
        """
        MATCH (repo:Repository)-[rel:PROVISIONS_PLATFORM]->(:Platform)
        WHERE repo.id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        DELETE rel
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )


def delete_orphan_platform_rows(
    session: Any,
    *,
    evidence_source: str,
) -> None:
    """Delete detached finalization-owned platform nodes."""

    session.run(
        """
        MATCH (p:Platform)
        WHERE p.evidence_source = $evidence_source
          AND NOT (p)--()
        DELETE p
        """,
        evidence_source=evidence_source,
    )


def write_workload_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge workload nodes and repository `DEFINES` edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})
        MERGE (w:Workload {id: row.workload_id})
        SET w.type = 'workload',
            w.name = row.workload_name,
            w.kind = row.workload_kind,
            w.repo_id = row.repo_id,
            w.evidence_source = $evidence_source
        MERGE (repo)-[rel:DEFINES]->(w)
        SET rel.confidence = 1.0,
            rel.reason = 'Repository defines workload',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_instance_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge workload instances and `INSTANCE_OF` edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (w:Workload {id: row.workload_id})
        MERGE (i:WorkloadInstance {id: row.instance_id})
        SET i.type = 'workload_instance',
            i.name = row.workload_name,
            i.kind = row.workload_kind,
            i.environment = row.environment,
            i.workload_id = row.workload_id,
            i.repo_id = row.repo_id,
            i.evidence_source = $evidence_source
        MERGE (i)-[rel:INSTANCE_OF]->(w)
        SET rel.confidence = 1.0,
            rel.reason = 'Workload instance belongs to workload',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_deployment_source_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge deployment-source edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (i:WorkloadInstance {id: row.instance_id})
        MATCH (deployment_repo:Repository {id: row.deployment_repo_id})
        MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)
        SET rel.confidence = 0.98,
            rel.reason = 'Deployment manifests for workload instance live in deployment repository',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_runtime_platform_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge runtime platform nodes and `RUNS_ON` edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (i:WorkloadInstance {id: row.instance_id})
        MERGE (p:Platform {id: row.platform_id})
        ON CREATE SET p.evidence_source = $evidence_source
        SET p.type = 'platform',
            p.name = row.platform_name,
            p.kind = row.platform_kind,
            p.provider = row.platform_provider,
            p.environment = row.environment,
            p.region = row.platform_region,
            p.locator = row.platform_locator
        MERGE (i)-[rel:RUNS_ON]->(p)
        SET rel.confidence = 1.0,
            rel.reason = 'Workload instance runs on inferred platform',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_repo_dependency_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge repository dependency edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (source_repo:Repository {id: row.repo_id})
        MATCH (target_repo:Repository {id: row.target_repo_id})
        MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
        SET rel.confidence = 0.9,
            rel.reason = 'Runtime services list declares repository dependency',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_workload_dependency_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge workload dependency edges only when the target workload already exists."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (source:Workload {id: row.workload_id})
        MATCH (target:Workload {id: row.target_workload_id})
        MERGE (source)-[rel:DEPENDS_ON]->(target)
        SET rel.confidence = 0.9,
            rel.reason = 'Runtime services list declares workload dependency',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )


def write_infrastructure_platform_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
) -> None:
    """Merge infrastructure platform nodes and `PROVISIONS_PLATFORM` edges in batches."""

    if not rows:
        return
    _run_batched_write(
        session,
        """
        UNWIND $rows AS row
        MATCH (repo:Repository {id: row.repo_id})
        MERGE (p:Platform {id: row.platform_id})
        ON CREATE SET p.evidence_source = $evidence_source
        SET p.type = 'platform',
            p.name = row.platform_name,
            p.kind = row.platform_kind,
            p.provider = row.platform_provider,
            p.environment = row.platform_environment,
            p.region = row.platform_region,
            p.locator = row.platform_locator
        MERGE (repo)-[rel:PROVISIONS_PLATFORM]->(p)
        SET rel.confidence = 0.98,
            rel.reason = 'Terraform cluster and module data declare platform provisioning',
            rel.evidence_source = $evidence_source
        """,
        rows,
        evidence_source=evidence_source,
    )
