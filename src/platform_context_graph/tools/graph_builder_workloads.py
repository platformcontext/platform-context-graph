"""Workload graph materialization helpers for indexed repositories."""

from __future__ import annotations

from pathlib import Path
import re
from typing import Any, Iterable

from .graph_builder_platforms import (
    materialize_infrastructure_platforms,
    materialize_runtime_platform,
)
from .languages.runtime_dependencies import extract_runtime_service_dependencies

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


def materialize_workloads(
    builder: Any,
    *,
    info_logger_fn: Any,
) -> dict[str, int]:
    """Materialize canonical workload nodes from indexed repo and Argo metadata.

    Args:
        builder: GraphBuilder facade instance.
        info_logger_fn: Informational logger callable.

    Returns:
        Counts of nodes and edges created or refreshed.
    """

    stats = {"workloads": 0, "instances": 0, "deployment_sources": 0}
    seen_workloads: set[str] = set()
    seen_instances: set[str] = set()
    seen_deployment_sources: set[tuple[str, str]] = set()

    with builder.driver.session() as session:
        candidate_rows = session.run("""
            MATCH (repo:Repository)
            OPTIONAL MATCH (repo)-[:CONTAINS*]->(:File)-[:CONTAINS]->(k:K8sResource)
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
            source_roots_key="source_roots",
            source_path_key="source_path",
            source_paths_key="source_paths",
            ).data()

        for row in candidate_rows:
            repo_id = row.get("repo_id")
            repo_name = row.get("repo_name")
            if not repo_id or not repo_name:
                continue

            workload_id = f"workload:{repo_name}"
            workload_kind = _infer_workload_kind(
                repo_name, row.get("resource_kinds", [])
            )
            session.run(
                """
                MATCH (repo:Repository {id: $repo_id})
                MERGE (w:Workload {id: $workload_id})
                SET w.type = 'workload',
                    w.name = $workload_name,
                    w.kind = $workload_kind,
                    w.repo_id = $repo_id
                MERGE (repo)-[rel:DEFINES]->(w)
                SET rel.confidence = 1.0,
                    rel.reason = 'Repository defines workload'
                """,
                repo_id=repo_id,
                repo_name=repo_name,
                workload_id=workload_id,
                workload_kind=workload_kind,
                workload_name=repo_name,
            )
            if workload_id not in seen_workloads:
                seen_workloads.add(workload_id)
                stats["workloads"] += 1

            source_roots = _normalize_source_roots(row.get("source_roots"))
            environments: list[str] = []
            deployment_repo_id = row.get("deployment_repo_id")
            if deployment_repo_id and source_roots:
                environment_rows = session.run(
                    """
                    MATCH (deployment_repo:Repository {id: $deployment_repo_id})-[:CONTAINS*]->(f:File)
                    WHERE any(source_root IN $source_roots
                        WHERE trim(source_root) <> ''
                          AND f.relative_path STARTS WITH trim(source_root))
                    RETURN deployment_repo.id as deployment_repo_id,
                           f.relative_path as relative_path
                    """,
                    deployment_repo_id=deployment_repo_id,
                    source_roots=source_roots,
                ).data()
                environments = _extract_overlay_environments(
                    row.get("relative_path", "") for row in environment_rows
                )

            if not environments:
                environments = [
                    namespace
                    for namespace in row.get("namespaces", [])
                    if namespace and namespace.strip()
                ]

            for environment in environments:
                instance_id = f"workload-instance:{repo_name}:{environment}"
                session.run(
                    """
                    MATCH (w:Workload {id: $workload_id})
                    MERGE (i:WorkloadInstance {id: $instance_id})
                    SET i.type = 'workload_instance',
                        i.name = $workload_name,
                        i.kind = $workload_kind,
                        i.environment = $environment,
                        i.workload_id = $workload_id,
                        i.repo_id = $repo_id
                    MERGE (i)-[rel:INSTANCE_OF]->(w)
                    SET rel.confidence = 1.0,
                        rel.reason = 'Workload instance belongs to workload'
                    """,
                    environment=environment,
                    instance_id=instance_id,
                    repo_id=repo_id,
                    workload_id=workload_id,
                    workload_kind=workload_kind,
                    workload_name=repo_name,
                )
                if instance_id not in seen_instances:
                    seen_instances.add(instance_id)
                    stats["instances"] += 1

                if deployment_repo_id:
                    session.run(
                        """
                        MATCH (i:WorkloadInstance {id: $instance_id})
                        MATCH (deployment_repo:Repository {id: $deployment_repo_id})
                        MERGE (i)-[rel:DEPLOYMENT_SOURCE]->(deployment_repo)
                        SET rel.confidence = 0.98,
                            rel.reason = 'Deployment manifests for workload instance live in deployment repository'
                        """,
                        deployment_repo_id=deployment_repo_id,
                        environment=environment,
                        instance_id=instance_id,
                        workload_name=repo_name,
                    )
                    deployment_signature = (instance_id, deployment_repo_id)
                    if deployment_signature not in seen_deployment_sources:
                        seen_deployment_sources.add(deployment_signature)
                        stats["deployment_sources"] += 1

                materialize_runtime_platform(
                    session,
                    instance_id=instance_id,
                    environment=environment,
                    workload_name=repo_name,
                    resource_kinds=row.get("resource_kinds", []),
                )

            _materialize_runtime_dependencies(
                session,
                repo_id=repo_id,
                repo_name=repo_name,
                workload_id=workload_id,
            )

        materialize_infrastructure_platforms(session)

    if stats["workloads"] > 0:
        info_logger_fn(
            "Workload materialization created "
            f"{stats['workloads']} workloads, {stats['instances']} instances, "
            f"and {stats['deployment_sources']} deployment-source edges"
        )
    else:
        info_logger_fn("Workload materialization found no deployable repositories")
    return stats


def _materialize_runtime_dependencies(
    session: Any,
    *,
    repo_id: str,
    repo_name: str,
    workload_id: str,
) -> None:
    """Create repo and workload dependency edges from runtime service lists."""
    file_rows = session.run(
        """
        MATCH (repo:Repository {id: $repo_id})-[:CONTAINS*]->(f:File)
        WHERE f.name IN [$typescript_entrypoint, $javascript_entrypoint]
        RETURN f.path as path, f.relative_path as relative_path
        ORDER BY f.relative_path
        """,
        repo_id=repo_id,
        typescript_entrypoint=f"{repo_name}.ts",
        javascript_entrypoint=f"{repo_name}.js",
    ).data()

    dependencies: list[str] = []
    seen_dependencies: set[str] = set()
    for row in file_rows:
        path = Path(str(row.get("path") or "")).expanduser()
        if not path.is_file():
            continue
        dependency_names = extract_runtime_service_dependencies(
            path.read_text(encoding="utf-8"),
            workload_name=repo_name,
        )
        for dependency_name in dependency_names:
            if dependency_name in seen_dependencies:
                continue
            seen_dependencies.add(dependency_name)
            dependencies.append(dependency_name)

    for dependency_name in dependencies:
        target_repo = session.run(
            """
            MATCH (target_repo:Repository)
            WHERE target_repo.name = $dependency_name
            RETURN target_repo.id as repo_id, target_repo.name as repo_name
            LIMIT 1
            """,
            dependency_name=dependency_name,
        ).data()
        if not target_repo:
            continue
        target_repo_id = target_repo[0].get("repo_id")
        if not target_repo_id:
            continue
        session.run(
            """
            MATCH (source_repo:Repository {id: $repo_id})
            MATCH (target_repo:Repository {id: $target_repo_id})
            MERGE (source_repo)-[rel:DEPENDS_ON]->(target_repo)
            SET rel.confidence = 0.9,
                rel.reason = 'Runtime services list declares repository dependency'
            """,
            dependency_name=dependency_name,
            repo_id=repo_id,
            target_repo_id=target_repo_id,
        )
        session.run(
            """
            MATCH (source:Workload {id: $workload_id})
            MATCH (target_repo:Repository {id: $target_repo_id})
            MERGE (target:Workload {id: $target_workload_id})
            ON CREATE SET target.type = 'workload',
                          target.name = $dependency_name,
                          target.kind = 'service',
                          target.repo_id = $target_repo_id
            MERGE (target_repo)-[:DEFINES]->(target)
            MERGE (source)-[rel:DEPENDS_ON]->(target)
            SET rel.confidence = 0.9,
                rel.reason = 'Runtime services list declares workload dependency'
            """,
            dependency_name=dependency_name,
            target_repo_id=target_repo_id,
            target_workload_id=f"workload:{dependency_name}",
            workload_id=workload_id,
        )
__all__ = ["materialize_workloads"]
