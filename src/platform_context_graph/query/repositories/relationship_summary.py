"""Repository-centered runtime and deployment relationship summaries."""

from __future__ import annotations

from typing import Any

from ...runtime.status_store import (
    get_repository_coverage as get_runtime_repository_coverage,
)
from .common import canonical_repository_ref
from .coverage_data import coverage_summary_from_row
from .graph_counts import repository_scope, repository_scope_predicate

_REPO_PROJECTION_PARAMS = {
    "local_path_key": "local_path",
    "remote_url_key": "remote_url",
    "repo_slug_key": "repo_slug",
    "has_remote_key": "has_remote",
}

_DEPLOYMENT_QUERY_PARAMS = {
    "project_key": "project",
    "dest_namespace_key": "dest_namespace",
    "source_path_key": "source_path",
    "source_repos_key": "source_repos",
    "source_paths_key": "source_paths",
    "source_roots_key": "source_roots",
}

__all__ = ["build_relationship_summary"]


def build_relationship_summary(
    session: Any, repo_ref: dict[str, Any]
) -> dict[str, Any]:
    """Build the shared runtime/deployment summary for one repository."""

    coverage_row = get_runtime_repository_coverage(repo_id=repo_ref["id"])
    coverage = coverage_summary_from_row(coverage_row)
    runtime_platforms = _fetch_runtime_platforms(session, repo_ref)
    provisioned_platforms = _fetch_provisioned_platforms(session, repo_ref)
    platforms = _dedupe_rows(runtime_platforms + provisioned_platforms)
    deploys_from = _fetch_deploys_from(session, repo_ref)
    discovers_config_in = _fetch_discovers_config_in(session, repo_ref)
    provisioned_by = _fetch_provisioned_by(session, repo_ref)
    provisions_dependencies_for = _fetch_provisions_dependencies_for(
        session,
        repo_ref,
    )
    iac_relationships = _fetch_iac_relationships(session, repo_ref)
    deployment_chain = _build_deployment_chain(
        repo_ref=repo_ref,
        deploys_from=deploys_from,
        discovers_config_in=discovers_config_in,
        runtime_platforms=runtime_platforms,
        provisioned_by=provisioned_by,
        provisions_dependencies_for=provisions_dependencies_for,
    )
    environments = _collect_environments(
        runtime_platforms=runtime_platforms,
        provisioned_platforms=provisioned_platforms,
        provisioned_by=provisioned_by,
        provisions_dependencies_for=provisions_dependencies_for,
    )
    limitations = _build_limitations(
        coverage=coverage,
        platforms=platforms,
        deploys_from=deploys_from,
        discovers_config_in=discovers_config_in,
        provisioned_by=provisioned_by,
        provisions_dependencies_for=provisions_dependencies_for,
        iac_relationships=iac_relationships,
        deployment_chain=deployment_chain,
        environments=environments,
    )
    summary = {
        "platform_count": len(
            {platform["id"] for platform in platforms if platform.get("id")}
        ),
        "deployment_source_count": len(deploys_from),
        "config_source_count": len(discovers_config_in),
        "provisioned_by_count": len(provisioned_by),
        "provisions_dependencies_for_count": len(provisions_dependencies_for),
        "iac_relationship_count": len(iac_relationships),
        "deployment_chain_length": len(deployment_chain),
        "environment_count": len(environments),
        "coverage_state": coverage["completeness_state"] if coverage else None,
        "graph_available": bool(coverage["graph_available"]) if coverage else False,
        "server_content_available": (
            bool(coverage["server_content_available"]) if coverage else False
        ),
    }
    return {
        "coverage": coverage,
        "platforms": platforms,
        "deploys_from": deploys_from,
        "discovers_config_in": discovers_config_in,
        "provisioned_by": provisioned_by,
        "provisions_dependencies_for": provisions_dependencies_for,
        "iac_relationships": iac_relationships,
        "deployment_chain": deployment_chain,
        "environments": environments,
        "summary": summary,
        "limitations": limitations,
    }


def _query_params(repo_ref: dict[str, Any]) -> dict[str, Any]:
    """Build the shared query parameters for one repository-scoped summary."""

    params = repository_scope(repo_ref)
    params.update(_REPO_PROJECTION_PARAMS)
    params.update(_DEPLOYMENT_QUERY_PARAMS)
    return params


def _fetch_runtime_platforms(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return runtime platforms reached through workload instances."""

    direct_rows = session.run(
        f"""
        MATCH (r:Repository)-[:RUNS_ON]->(p:Platform)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT p.id as id,
               p.name as name,
               p.kind as kind,
               p.provider as provider,
               p.environment as environment,
               NULL as workload_instance_id,
               NULL as workload_environment
        ORDER BY p.kind, p.name
        """,
        **_query_params(repo_ref),
    ).data()
    instance_rows = session.run(
        f"""
        MATCH (r:Repository)
        WHERE {repository_scope_predicate()}
        MATCH (r)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)
              -[:RUNS_ON]->(p:Platform)
        RETURN DISTINCT p.id as id,
               p.name as name,
               p.kind as kind,
               p.provider as provider,
               p.environment as environment,
               i.id as workload_instance_id,
               i.environment as workload_environment
        ORDER BY p.kind, p.name
        """,
        **_query_params(repo_ref),
    ).data()
    return _dedupe_rows(
        [
            {
                **row,
                "relationship_type": "RUNS_ON",
                "source": "runtime",
            }
            for row in [*direct_rows, *instance_rows]
        ]
    )


def _fetch_provisioned_platforms(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return platforms provisioned directly by the repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)
        WHERE {repository_scope_predicate()}
        MATCH (r)-[:PROVISIONS_PLATFORM]->(p:Platform)
        RETURN DISTINCT p.id as id,
               p.name as name,
               p.kind as kind,
               p.provider as provider,
               p.environment as environment
        ORDER BY p.kind, p.name
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **row,
            "relationship_type": "PROVISIONS_PLATFORM",
            "source": "provisioned",
        }
        for row in rows
    ]


def _fetch_deploys_from(session: Any, repo_ref: dict[str, Any]) -> list[dict[str, Any]]:
    """Return canonical deployment-source repositories for the repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:DEPLOYS_FROM]->(dep:Repository)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT dep.id as id,
               dep.name as name,
               dep.path as path,
               coalesce(dep[$local_path_key], dep.path) as local_path,
               dep[$remote_url_key] as remote_url,
               dep[$repo_slug_key] as repo_slug,
               coalesce(dep[$has_remote_key], false) as has_remote
        ORDER BY dep.name
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **canonical_repository_ref(row),
            "relationship_type": "DEPLOYS_FROM",
        }
        for row in rows
    ]


def _fetch_discovers_config_in(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return canonical config-source repositories for the repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:DISCOVERS_CONFIG_IN]->(cfg:Repository)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT cfg.id as id,
               cfg.name as name,
               cfg.path as path,
               coalesce(cfg[$local_path_key], cfg.path) as local_path,
               cfg[$remote_url_key] as remote_url,
               cfg[$repo_slug_key] as repo_slug,
               coalesce(cfg[$has_remote_key], false) as has_remote
        ORDER BY cfg.name
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **canonical_repository_ref(row),
            "relationship_type": "DISCOVERS_CONFIG_IN",
        }
        for row in rows
    ]


def _fetch_provisioned_by(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return canonical infrastructure repositories that provision this repository."""

    rows = session.run(
        f"""
        MATCH (prov:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(r:Repository)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT prov.id as id,
               prov.name as name,
               prov.path as path,
               coalesce(prov[$local_path_key], prov.path) as local_path,
               prov[$remote_url_key] as remote_url,
               prov[$repo_slug_key] as repo_slug,
               coalesce(prov[$has_remote_key], false) as has_remote
        ORDER BY prov.name
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **canonical_repository_ref(row),
            "relationship_type": "PROVISIONED_BY",
        }
        for row in rows
    ]


def _fetch_provisions_dependencies_for(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return canonical repositories provisioned by this infrastructure repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:PROVISIONS_DEPENDENCY_FOR]->(dep:Repository)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT dep.id as id,
               dep.name as name,
               dep.path as path,
               coalesce(dep[$local_path_key], dep.path) as local_path,
               dep[$remote_url_key] as remote_url,
               dep[$repo_slug_key] as repo_slug,
               coalesce(dep[$has_remote_key], false) as has_remote
        ORDER BY dep.name
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **canonical_repository_ref(row),
            "relationship_type": "PROVISIONS_DEPENDENCY_FOR",
        }
        for row in rows
    ]


def _fetch_iac_relationships(
    session: Any, repo_ref: dict[str, Any]
) -> list[dict[str, Any]]:
    """Return infrastructure graph relationships relevant to repository context."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:CONTAINS*]->(f1:File)-[:CONTAINS]->(n1)
              -[rel]->(n2)<-[:CONTAINS]-(f2:File)<-[:CONTAINS*]-(r)
        WHERE {repository_scope_predicate()}
          AND type(rel) IN [
            'SELECTS', 'CONFIGURES', 'PATCHES', 'ROUTES_TO',
            'SATISFIED_BY', 'IMPLEMENTED_BY', 'RUNS_IMAGE',
            'USES_IAM'
        ]
        RETURN DISTINCT type(rel) as type,
               n1.name as from_name,
               labels(n1)[0] as from_kind,
               n2.name as to_name,
               labels(n2)[0] as to_kind
        LIMIT 100
        """,
        **_query_params(repo_ref),
    ).data()
    return [
        {
            **row,
            "relationship_type": row.get("type"),
        }
        for row in rows
    ]


def _build_deployment_chain(
    *,
    repo_ref: dict[str, Any],
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    runtime_platforms: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    provisions_dependencies_for: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Build a lightweight end-to-end deployment chain for the repository."""

    chain: list[dict[str, Any]] = []
    for row in deploys_from:
        chain.append(
            {
                "relationship_type": row["relationship_type"],
                "source_name": repo_ref.get("name"),
                "source_id": repo_ref.get("id"),
                "target_name": row.get("name") or row.get("source_path"),
                "target_kind": "Repository",
                **row,
            }
        )
    for row in discovers_config_in:
        chain.append(
            {
                "relationship_type": row["relationship_type"],
                "source_name": repo_ref.get("name"),
                "source_id": repo_ref.get("id"),
                "target_name": row.get("name") or row.get("source_repos"),
                "target_kind": "Repository",
                **row,
            }
        )
    for row in runtime_platforms:
        chain.append(
            {
                "relationship_type": row["relationship_type"],
                "source_name": row.get("workload_instance_id") or repo_ref.get("name"),
                "source_id": row.get("workload_instance_id") or repo_ref.get("id"),
                "target_name": row.get("name"),
                "target_kind": "Platform",
                **row,
            }
        )
    for row in provisioned_by:
        chain.append(
            {
                "relationship_type": row["relationship_type"],
                "source_name": row.get("name"),
                "source_id": row.get("id"),
                "target_name": repo_ref.get("name"),
                "target_kind": "Repository",
                **row,
            }
        )
    for row in provisions_dependencies_for:
        chain.append(
            {
                "relationship_type": row["relationship_type"],
                "source_name": repo_ref.get("name"),
                "source_id": repo_ref.get("id"),
                "target_name": row.get("name"),
                "target_kind": "Repository",
                **row,
            }
        )
    return _dedupe_rows(chain)


def _collect_environments(
    *,
    runtime_platforms: list[dict[str, Any]],
    provisioned_platforms: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    provisions_dependencies_for: list[dict[str, Any]],
) -> list[str]:
    """Collect normalized environment hints from runtime and infra rows."""

    environments: set[str] = set()
    for row in runtime_platforms + provisioned_platforms:
        for key in ("environment", "workload_environment", "platform_environment"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                environments.add(value.strip())
    for row in provisioned_by + provisions_dependencies_for:
        for key in ("platform_environment", "environment"):
            value = row.get(key)
            if isinstance(value, str) and value.strip():
                environments.add(value.strip())
    return sorted(environments)


def _build_limitations(
    *,
    coverage: dict[str, Any] | None,
    platforms: list[dict[str, Any]],
    deploys_from: list[dict[str, Any]],
    discovers_config_in: list[dict[str, Any]],
    provisioned_by: list[dict[str, Any]],
    provisions_dependencies_for: list[dict[str, Any]],
    iac_relationships: list[dict[str, Any]],
    deployment_chain: list[dict[str, Any]],
    environments: list[str],
) -> list[str]:
    """Return truthful limitations derived from repository coverage."""

    del platforms, deploys_from, discovers_config_in
    del provisioned_by, provisions_dependencies_for, iac_relationships
    del deployment_chain, environments
    if coverage is None:
        return ["graph_partial", "content_partial"]
    return list(coverage.get("limitations") or [])


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows with duplicates removed while preserving order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(k), repr(v)) for k, v in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped
