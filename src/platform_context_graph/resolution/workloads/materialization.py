"""Workload graph materialization helpers for indexed repositories."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from ..platforms import materialize_infrastructure_platforms_for_repo_paths
from .batches import retract_instance_rows
from .batches import retract_repo_dependency_rows
from .batches import retract_stale_workload_rows
from .batches import retract_workload_dependency_rows
from .batches import write_deployment_source_rows
from .batches import write_instance_rows
from .batches import write_runtime_platform_rows
from .batches import write_workload_rows
from .dependency_support import materialize_runtime_dependencies
from .projection import build_projection_rows
from ...utils.debug_log import emit_log_call

_EVIDENCE_SOURCE = "finalization/workloads"
_OVERLAY_ENVIRONMENT_RE = re.compile(r"(?:^|/)overlays/([^/]+)/")


def _normalize_source_roots(raw_value: Any) -> list[str]:
    """Normalize stored ApplicationSet roots into a stable string list."""

    if isinstance(raw_value, str):
        values = raw_value.split(",")
    elif isinstance(raw_value, Iterable):
        values = [str(value) for value in raw_value]
    else:
        values = []
    roots: list[str] = []
    for value in values:
        root = str(value).strip()
        if not root or root in roots:
            continue
        roots.append(root)
    return roots


def _extract_overlay_environments(paths: Iterable[str]) -> list[str]:
    """Extract environment names from repo-relative overlay paths."""

    environments: list[str] = []
    for raw_path in paths:
        match = _OVERLAY_ENVIRONMENT_RE.search(str(raw_path))
        if not match:
            continue
        environment = match.group(1).strip()
        if environment and environment not in environments:
            environments.append(environment)
    return environments


def _normalize_repo_paths(
    committed_repo_paths: list[Path] | None,
) -> list[str] | None:
    """Convert repo path filters into stored repository path strings."""

    if not committed_repo_paths:
        return None
    return [str(path.resolve()) for path in committed_repo_paths]


def _merge_metric_totals(
    totals: dict[str, int],
    current: dict[str, int],
) -> dict[str, int]:
    """Merge one integer metrics payload into the running totals."""

    for key, value in current.items():
        totals[key] = totals.get(key, 0) + int(value)
    return totals


def _emit_workload_progress(
    *,
    info_logger_fn: Any,
    progress_callback: Any | None,
    **details: object,
) -> None:
    """Emit one structured workload progress event to logs and callbacks."""

    if callable(progress_callback):
        progress_callback(**details)
    emit_log_call(
        info_logger_fn,
        "Workload finalization progress",
        event_name="index.finalization.workloads.progress",
        extra_keys={key: value for key, value in details.items() if value is not None},
    )


def _load_candidate_rows(
    session: Any,
    *,
    repo_paths: list[str] | None,
) -> list[dict[str, object]]:
    """Load workload candidates from repository and GitOps graph signal."""

    return session.run(
        """
        MATCH (repo:Repository)
        WHERE $repo_paths IS NULL OR repo.path IN $repo_paths
        OPTIONAL MATCH (repo)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(k:K8sResource)
        WHERE k.name = repo.name
        WITH repo,
             collect(DISTINCT toLower(coalesce(k.kind, ''))) as resource_kinds,
             collect(DISTINCT coalesce(k.namespace, '')) as namespaces
        OPTIONAL MATCH (app)-[source_rel]->(deployment_repo:Repository)
        WHERE (app:ArgoCDApplication OR app:ArgoCDApplicationSet)
          AND type(source_rel) = 'SOURCES_FROM'
          AND app.name = repo.name
        WITH repo,
             resource_kinds,
             namespaces,
             collect(DISTINCT deployment_repo.id) as deployment_repo_ids,
             collect(DISTINCT deployment_repo.name) as deployment_repo_names,
             collect(
                 DISTINCT coalesce(
                     app[$source_roots_key],
                     coalesce(app[$source_path_key], app[$source_paths_key], '')
                 )
             ) as source_roots
        WHERE size(resource_kinds) > 0 OR size(deployment_repo_ids) > 0
        RETURN repo.id as repo_id,
               repo.name as repo_name,
               CASE
                   WHEN size(deployment_repo_ids) > 0
                   THEN deployment_repo_ids[0]
                   ELSE NULL
               END as deployment_repo_id,
               CASE
                   WHEN size(deployment_repo_names) > 0
                   THEN deployment_repo_names[0]
                   ELSE NULL
               END as deployment_repo_name,
               resource_kinds,
               namespaces,
               source_roots
        ORDER BY repo.name
        """,
        repo_paths=repo_paths,
        source_roots_key="source_roots",
        source_path_key="source_path",
        source_paths_key="source_paths",
    ).data()


def _load_target_repo_rows(
    session: Any,
    *,
    repo_paths: list[str] | None,
) -> list[dict[str, object]]:
    """Load all targeted repositories, including ones without active workloads."""

    return session.run(
        """
        MATCH (repo:Repository)
        WHERE $repo_paths IS NULL OR repo.path IN $repo_paths
        RETURN repo.id as target_repo_id,
               repo.name as target_repo_name
        ORDER BY repo.name
        """,
        repo_paths=repo_paths,
    ).data()


def _load_deployment_environments(
    session: Any,
    *,
    candidate_rows: list[dict[str, object]],
) -> dict[str, list[str]]:
    """Load overlay environments for deployment repositories in one query."""

    deployment_rows = [
        {
            "deployment_repo_id": row.get("deployment_repo_id"),
            "source_roots": _normalize_source_roots(row.get("source_roots")),
        }
        for row in candidate_rows
        if row.get("deployment_repo_id")
        and _normalize_source_roots(row.get("source_roots"))
    ]
    if not deployment_rows:
        return {}

    environment_rows = session.run(
        """
        UNWIND $rows AS row
        MATCH (deployment_repo:Repository {id: row.deployment_repo_id})-[:REPO_CONTAINS]->(f:File)
        WHERE any(source_root IN row.source_roots
            WHERE trim(source_root) <> ''
              AND f.relative_path STARTS WITH trim(source_root))
        RETURN deployment_repo.id as deployment_repo_id,
               f.relative_path as relative_path
        ORDER BY deployment_repo.id, f.relative_path
        """,
        rows=deployment_rows,
    ).data()

    environments_by_repo: dict[str, list[str]] = {}
    for row in environment_rows:
        deployment_repo_id = str(row.get("deployment_repo_id") or "")
        if not deployment_repo_id:
            continue
        environments = environments_by_repo.setdefault(deployment_repo_id, [])
        for environment in _extract_overlay_environments(
            [str(row.get("relative_path") or "")]
        ):
            if environment not in environments:
                environments.append(environment)
    return environments_by_repo


def materialize_workloads(
    builder: Any,
    *,
    info_logger_fn: Any,
    committed_repo_paths: list[Path] | None = None,
    progress_callback: Any | None = None,
) -> dict[str, int]:
    """Materialize canonical workload nodes from indexed repo and Argo metadata."""

    repo_paths = _normalize_repo_paths(committed_repo_paths)
    metrics = {
        "candidate_repo_count": 0,
        "cleanup_deleted_edges": 0,
        "cleanup_deleted_nodes": 0,
        "candidates_processed": 0,
        "candidates_total": 0,
        "deployment_sources": 0,
        "deployment_sources_projected": 0,
        "instances": 0,
        "instances_projected": 0,
        "repo_dependency_edges_projected": 0,
        "runtime_platform_edges_projected": 0,
        "targeted_repo_count": 0,
        "workloads": 0,
        "workloads_projected": 0,
        "workload_dependency_edges_projected": 0,
        "write_chunk_count": 0,
    }
    with builder.driver.session() as session:
        target_repo_rows = _load_target_repo_rows(session, repo_paths=repo_paths)
        candidate_rows = _load_candidate_rows(session, repo_paths=repo_paths)
        deployment_environments = _load_deployment_environments(
            session,
            candidate_rows=candidate_rows,
        )
        (
            stats,
            workload_rows,
            instance_rows,
            deployment_source_rows,
            runtime_platform_rows,
            repo_descriptors,
        ) = build_projection_rows(
            candidate_rows,
            deployment_environments=deployment_environments,
        )

        def _progress(**details: object) -> None:
            """Mirror workload progress to both logs and the stage callback."""

            _emit_workload_progress(
                info_logger_fn=info_logger_fn,
                progress_callback=progress_callback,
                **details,
            )

        target_repo_ids = [
            str(row.get("target_repo_id") or "")
            for row in target_repo_rows
            if str(row.get("target_repo_id") or "").strip()
        ]
        metrics["targeted_repo_count"] = len(target_repo_ids)
        active_workload_ids = [
            str(row.get("workload_id") or "")
            for row in workload_rows
            if str(row.get("workload_id") or "").strip()
        ]
        metrics["candidate_repo_count"] = len(candidate_rows)
        metrics["candidates_processed"] = len(candidate_rows)
        metrics["candidates_total"] = len(candidate_rows)
        metrics["workloads"] = stats["workloads"]
        metrics["workloads_projected"] = stats["workloads"]
        metrics["instances"] = stats["instances"]
        metrics["instances_projected"] = stats["instances"]
        metrics["deployment_sources"] = stats["deployment_sources"]
        metrics["deployment_sources_projected"] = stats["deployment_sources"]
        metrics["runtime_platform_edges_projected"] = len(runtime_platform_rows)
        _progress(
            status="running",
            operation="gather_completed",
            candidate_repo_count=metrics["candidate_repo_count"],
            candidates_processed=metrics["candidates_processed"],
            candidates_total=metrics["candidates_total"],
            deployment_sources_projected=metrics["deployment_sources_projected"],
            instances_projected=metrics["instances_projected"],
            runtime_platform_edges_projected=metrics["runtime_platform_edges_projected"],
            targeted_repo_count=metrics["targeted_repo_count"],
            workloads_projected=metrics["workloads_projected"],
        )
        _merge_metric_totals(
            metrics,
            retract_repo_dependency_rows(
                session,
                target_repo_ids,
                evidence_source=_EVIDENCE_SOURCE,
            ),
        )
        _progress(
            status="running",
            operation="cleanup_completed",
            cleanup_pass="repo_dependencies",
            cleanup_deleted_edges=metrics["cleanup_deleted_edges"],
            cleanup_deleted_nodes=metrics["cleanup_deleted_nodes"],
            targeted_repo_count=metrics["targeted_repo_count"],
        )
        _merge_metric_totals(
            metrics,
            retract_workload_dependency_rows(
                session,
                target_repo_ids,
                active_workload_ids=active_workload_ids,
                evidence_source=_EVIDENCE_SOURCE,
            ),
        )
        _progress(
            status="running",
            operation="cleanup_completed",
            cleanup_pass="workload_dependencies",
            cleanup_deleted_edges=metrics["cleanup_deleted_edges"],
            cleanup_deleted_nodes=metrics["cleanup_deleted_nodes"],
            targeted_repo_count=metrics["targeted_repo_count"],
        )
        _merge_metric_totals(
            metrics,
            retract_stale_workload_rows(
                session,
                target_repo_ids,
                active_workload_ids=active_workload_ids,
                evidence_source=_EVIDENCE_SOURCE,
            ),
        )
        _progress(
            status="running",
            operation="cleanup_completed",
            cleanup_pass="stale_workloads",
            cleanup_deleted_edges=metrics["cleanup_deleted_edges"],
            cleanup_deleted_nodes=metrics["cleanup_deleted_nodes"],
            targeted_repo_count=metrics["targeted_repo_count"],
        )
        _merge_metric_totals(
            metrics,
            retract_instance_rows(
                session,
                target_repo_ids,
                evidence_source=_EVIDENCE_SOURCE,
            ),
        )
        _progress(
            status="running",
            operation="cleanup_completed",
            cleanup_pass="instances",
            cleanup_deleted_edges=metrics["cleanup_deleted_edges"],
            cleanup_deleted_nodes=metrics["cleanup_deleted_nodes"],
            targeted_repo_count=metrics["targeted_repo_count"],
        )
        _merge_metric_totals(
            metrics,
            write_workload_rows(
                session,
                workload_rows,
                evidence_source=_EVIDENCE_SOURCE,
                progress_callback=_progress,
            ),
        )
        _merge_metric_totals(
            metrics,
            write_instance_rows(
                session,
                instance_rows,
                evidence_source=_EVIDENCE_SOURCE,
                progress_callback=_progress,
            ),
        )
        _merge_metric_totals(
            metrics,
            write_deployment_source_rows(
                session,
                deployment_source_rows,
                evidence_source=_EVIDENCE_SOURCE,
                progress_callback=_progress,
            ),
        )
        _merge_metric_totals(
            metrics,
            write_runtime_platform_rows(
                session,
                runtime_platform_rows,
                evidence_source=_EVIDENCE_SOURCE,
                progress_callback=_progress,
            ),
        )
        _merge_metric_totals(
            metrics,
            materialize_runtime_dependencies(
                session,
                repo_descriptors=repo_descriptors,
                evidence_source=_EVIDENCE_SOURCE,
                progress_callback=_progress,
            ),
        )
        _merge_metric_totals(
            metrics,
            materialize_infrastructure_platforms_for_repo_paths(
                session,
                repo_paths=committed_repo_paths,
                progress_callback=_progress,
            ),
        )

    if metrics["workloads_projected"] > 0:
        info_logger_fn(
            "Workload materialization created "
            f"{metrics['workloads_projected']} workloads, "
            f"{metrics['instances_projected']} instances, and "
            f"{metrics['deployment_sources_projected']} deployment-source edges"
        )
    else:
        info_logger_fn("Workload materialization found no deployable repositories")
    return metrics


__all__ = ["materialize_workloads"]
