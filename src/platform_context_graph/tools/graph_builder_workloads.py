"""Workload graph materialization helpers for indexed repositories."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .graph_builder_platforms import (
    canonical_platform_id,
    infer_runtime_platform_kind,
    materialize_infrastructure_platforms_for_repo_paths,
)
from .graph_builder_workload_batches import (
    retract_instance_rows,
    retract_repo_dependency_rows,
    retract_stale_workload_rows,
    retract_workload_dependency_rows,
    write_deployment_source_rows,
    write_instance_rows,
    write_runtime_platform_rows,
    write_workload_rows,
)
from .graph_builder_workload_dependency_support import (
    materialize_runtime_dependencies,
)

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


def _infer_workload_kind(name: str, resource_kinds: Iterable[str]) -> str:
    """Infer a workload kind from its name and matched runtime resources."""

    normalized = name.lower()
    if "cron" in normalized:
        return "cronjob"
    if "worker" in normalized:
        return "worker"
    if "consumer" in normalized:
        return "consumer"
    if "batch" in normalized:
        return "batch"
    normalized_resource_kinds = {str(kind).lower() for kind in resource_kinds if kind}
    if normalized_resource_kinds.intersection({"deployment", "service", "statefulset"}):
        return "service"
    return "service"


def _normalize_repo_paths(
    committed_repo_paths: list[Path] | None,
) -> list[str] | None:
    """Convert repo path filters into stored repository path strings."""

    if not committed_repo_paths:
        return None
    return [str(path.resolve()) for path in committed_repo_paths]


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


def _build_projection_rows(
    candidate_rows: list[dict[str, object]],
    *,
    deployment_environments: dict[str, list[str]],
) -> tuple[
    dict[str, int],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, object]],
    list[dict[str, str]],
]:
    """Build batched projection payloads from workload candidates."""

    stats = {"workloads": 0, "instances": 0, "deployment_sources": 0}
    workload_rows: list[dict[str, object]] = []
    instance_rows: list[dict[str, object]] = []
    deployment_source_rows: list[dict[str, object]] = []
    runtime_platform_rows: list[dict[str, object]] = []
    repo_descriptors: list[dict[str, str]] = []
    seen_workloads: set[str] = set()
    seen_instances: set[str] = set()
    seen_deployment_sources: set[tuple[str, str]] = set()
    seen_runtime_platforms: set[tuple[str, str]] = set()

    for row in candidate_rows:
        repo_id = str(row.get("repo_id") or "")
        repo_name = str(row.get("repo_name") or "")
        if not repo_id or not repo_name:
            continue
        workload_id = f"workload:{repo_name}"
        workload_kind = _infer_workload_kind(repo_name, row.get("resource_kinds", []))
        repo_descriptors.append(
            {
                "repo_id": repo_id,
                "repo_name": repo_name,
                "workload_id": workload_id,
            }
        )
        if workload_id not in seen_workloads:
            seen_workloads.add(workload_id)
            workload_rows.append(
                {
                    "repo_id": repo_id,
                    "workload_id": workload_id,
                    "workload_kind": workload_kind,
                    "workload_name": repo_name,
                }
            )
            stats["workloads"] += 1

        deployment_repo_id = str(row.get("deployment_repo_id") or "")
        environments = deployment_environments.get(deployment_repo_id, [])
        if not environments:
            environments = [
                namespace
                for namespace in row.get("namespaces", [])
                if namespace and str(namespace).strip()
            ]

        platform_kind = infer_runtime_platform_kind(row.get("resource_kinds", []))
        for environment in environments:
            instance_id = f"workload-instance:{repo_name}:{environment}"
            if instance_id not in seen_instances:
                seen_instances.add(instance_id)
                instance_rows.append(
                    {
                        "environment": environment,
                        "instance_id": instance_id,
                        "repo_id": repo_id,
                        "workload_id": workload_id,
                        "workload_kind": workload_kind,
                        "workload_name": repo_name,
                    }
                )
                stats["instances"] += 1
            if deployment_repo_id:
                deployment_signature = (instance_id, deployment_repo_id)
                if deployment_signature not in seen_deployment_sources:
                    seen_deployment_sources.add(deployment_signature)
                    deployment_source_rows.append(
                        {
                            "deployment_repo_id": deployment_repo_id,
                            "environment": environment,
                            "instance_id": instance_id,
                            "workload_name": repo_name,
                        }
                    )
                    stats["deployment_sources"] += 1
            if platform_kind is None:
                continue
            platform_id = canonical_platform_id(
                kind=platform_kind,
                provider=None,
                name=environment,
                environment=environment,
                region=None,
                locator=None,
            )
            if platform_id is None:
                continue
            platform_signature = (instance_id, platform_id)
            if platform_signature in seen_runtime_platforms:
                continue
            seen_runtime_platforms.add(platform_signature)
            runtime_platform_rows.append(
                {
                    "environment": environment,
                    "instance_id": instance_id,
                    "platform_id": platform_id,
                    "platform_kind": platform_kind,
                    "platform_locator": None,
                    "platform_name": environment,
                    "platform_provider": None,
                    "platform_region": None,
                }
            )

    return (
        stats,
        workload_rows,
        instance_rows,
        deployment_source_rows,
        runtime_platform_rows,
        repo_descriptors,
    )


def materialize_workloads(
    builder: Any,
    *,
    info_logger_fn: Any,
    committed_repo_paths: list[Path] | None = None,
) -> dict[str, int]:
    """Materialize canonical workload nodes from indexed repo and Argo metadata."""

    repo_paths = _normalize_repo_paths(committed_repo_paths)
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
        ) = _build_projection_rows(
            candidate_rows,
            deployment_environments=deployment_environments,
        )
        target_repo_ids = [
            str(row.get("target_repo_id") or "")
            for row in target_repo_rows
            if str(row.get("target_repo_id") or "").strip()
        ]
        active_workload_ids = [
            str(row.get("workload_id") or "")
            for row in workload_rows
            if str(row.get("workload_id") or "").strip()
        ]
        retract_repo_dependency_rows(
            session,
            target_repo_ids,
            evidence_source=_EVIDENCE_SOURCE,
        )
        retract_workload_dependency_rows(
            session,
            target_repo_ids,
            active_workload_ids=active_workload_ids,
            evidence_source=_EVIDENCE_SOURCE,
        )
        retract_stale_workload_rows(
            session,
            target_repo_ids,
            active_workload_ids=active_workload_ids,
            evidence_source=_EVIDENCE_SOURCE,
        )
        retract_instance_rows(
            session,
            target_repo_ids,
            evidence_source=_EVIDENCE_SOURCE,
        )
        write_workload_rows(
            session,
            workload_rows,
            evidence_source=_EVIDENCE_SOURCE,
        )
        write_instance_rows(
            session,
            instance_rows,
            evidence_source=_EVIDENCE_SOURCE,
        )
        write_deployment_source_rows(
            session,
            deployment_source_rows,
            evidence_source=_EVIDENCE_SOURCE,
        )
        write_runtime_platform_rows(
            session,
            runtime_platform_rows,
            evidence_source=_EVIDENCE_SOURCE,
        )
        materialize_runtime_dependencies(
            session,
            repo_descriptors=repo_descriptors,
            evidence_source=_EVIDENCE_SOURCE,
        )
        materialize_infrastructure_platforms_for_repo_paths(
            session,
            repo_paths=committed_repo_paths,
        )

    if stats["workloads"] > 0:
        info_logger_fn(
            "Workload materialization created "
            f"{stats['workloads']} workloads, {stats['instances']} instances, "
            f"and {stats['deployment_sources']} deployment-source edges"
        )
    else:
        info_logger_fn("Workload materialization found no deployable repositories")
    return stats


__all__ = ["materialize_workloads"]
