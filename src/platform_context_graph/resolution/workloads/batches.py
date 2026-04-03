"""Batched Neo4j projection helpers for workload finalization."""

from __future__ import annotations

from typing import Any, Iterable

from .metrics import merge_metrics
from .metrics import run_cleanup_query

_DEFAULT_BATCH_SIZE = 250
_EMPTY_WRITE_METRICS = {"write_chunk_count": 0, "written_row_count": 0}
_EMPTY_CLEANUP_METRICS = {"cleanup_deleted_edges": 0, "cleanup_deleted_nodes": 0}


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
    entity_name: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Execute one `UNWIND` write query in bounded chunks."""

    if not rows:
        return dict(_EMPTY_WRITE_METRICS)

    chunk_count = (len(rows) - 1) // _DEFAULT_BATCH_SIZE + 1
    for chunk_index, chunk in enumerate(_chunk_rows(rows), start=1):
        if callable(progress_callback):
            progress_callback(
                status="running",
                operation="write_chunk_started",
                entity=entity_name,
                chunk_count=chunk_count,
                chunk_index=chunk_index,
                chunk_row_count=len(chunk),
            )
        session.run(query, rows=chunk, evidence_source=evidence_source)
        if callable(progress_callback):
            progress_callback(
                status="running",
                operation="write_chunk_completed",
                entity=entity_name,
                chunk_count=chunk_count,
                chunk_index=chunk_index,
                chunk_row_count=len(chunk),
            )
    return {
        "write_chunk_count": chunk_count,
        "written_row_count": len(rows),
    }


def retract_repo_dependency_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> dict[str, int]:
    """Delete workload-owned repository dependencies for targeted repos."""

    if not repo_ids:
        return dict(_EMPTY_CLEANUP_METRICS)
    return run_cleanup_query(
        session,
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
) -> dict[str, int]:
    """Delete targeted workload dependencies while preserving active targets."""

    if not repo_ids:
        return dict(_EMPTY_CLEANUP_METRICS)
    metrics = run_cleanup_query(
        session,
        """
        MATCH (source:Workload)-[rel:DEPENDS_ON]->(:Workload)
        WHERE source.repo_id IN $repo_ids
          AND rel.evidence_source = $evidence_source
        DELETE rel
        """,
        repo_ids=repo_ids,
        evidence_source=evidence_source,
    )
    return merge_metrics(
        metrics,
        run_cleanup_query(
            session,
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
        ),
    )


def retract_stale_workload_rows(
    session: Any,
    repo_ids: list[str],
    *,
    active_workload_ids: list[str],
    evidence_source: str,
) -> dict[str, int]:
    """Delete stale targeted workload nodes without touching active ones."""

    if not repo_ids:
        return dict(_EMPTY_CLEANUP_METRICS)
    metrics = run_cleanup_query(
        session,
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
    return merge_metrics(
        metrics,
        run_cleanup_query(
            session,
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
        ),
    )


def retract_instance_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> dict[str, int]:
    """Delete targeted workload-instance state so it can be rebuilt cleanly."""

    if not repo_ids:
        return dict(_EMPTY_CLEANUP_METRICS)
    metrics = dict(_EMPTY_CLEANUP_METRICS)
    for relationship_type, target_label in (
        ("DEPLOYMENT_SOURCE", "Repository"),
        ("RUNS_ON", "Platform"),
        ("INSTANCE_OF", "Workload"),
    ):
        merge_metrics(
            metrics,
            run_cleanup_query(
                session,
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
            ),
        )
    return merge_metrics(
        metrics,
        run_cleanup_query(
            session,
            """
        MATCH (i:WorkloadInstance)
        WHERE i.repo_id IN $repo_ids
          AND i.evidence_source = $evidence_source
          AND NOT (i)--()
        DELETE i
        """,
            repo_ids=repo_ids,
            evidence_source=evidence_source,
        ),
    )


def retract_infrastructure_platform_rows(
    session: Any,
    repo_ids: list[str],
    *,
    evidence_source: str,
) -> dict[str, int]:
    """Delete targeted infrastructure platform edges before re-materializing."""

    if not repo_ids:
        return dict(_EMPTY_CLEANUP_METRICS)
    return run_cleanup_query(
        session,
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
) -> dict[str, int]:
    """Delete detached finalization-owned platform nodes."""

    return run_cleanup_query(
        session,
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
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge workload nodes and repository `DEFINES` edges in batches."""

    return _run_batched_write(
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
        entity_name="workloads",
        progress_callback=progress_callback,
    )


def write_instance_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge workload instances and `INSTANCE_OF` edges in batches."""

    return _run_batched_write(
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
        entity_name="instances",
        progress_callback=progress_callback,
    )


def write_deployment_source_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge deployment-source edges in batches."""

    return _run_batched_write(
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
        entity_name="deployment_sources",
        progress_callback=progress_callback,
    )


def write_runtime_platform_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge runtime platform nodes and `RUNS_ON` edges in batches."""

    return _run_batched_write(
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
        entity_name="runtime_platforms",
        progress_callback=progress_callback,
    )


def write_repo_dependency_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge repository dependency edges in batches."""

    return _run_batched_write(
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
        entity_name="repo_dependencies",
        progress_callback=progress_callback,
    )


def write_workload_dependency_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge workload dependency edges only when the target workload exists."""

    return _run_batched_write(
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
        entity_name="workload_dependencies",
        progress_callback=progress_callback,
    )


def write_infrastructure_platform_rows(
    session: Any,
    rows: list[dict[str, object]],
    *,
    evidence_source: str,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Merge infrastructure platform nodes and `PROVISIONS_PLATFORM` edges."""

    return _run_batched_write(
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
        entity_name="infrastructure_platforms",
        progress_callback=progress_callback,
    )


__all__ = [
    "delete_orphan_platform_rows",
    "retract_infrastructure_platform_rows",
    "retract_instance_rows",
    "retract_repo_dependency_rows",
    "retract_stale_workload_rows",
    "retract_workload_dependency_rows",
    "write_deployment_source_rows",
    "write_infrastructure_platform_rows",
    "write_instance_rows",
    "write_repo_dependency_rows",
    "write_runtime_platform_rows",
    "write_workload_dependency_rows",
    "write_workload_rows",
]
