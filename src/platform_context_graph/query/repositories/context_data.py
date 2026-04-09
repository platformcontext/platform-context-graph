"""Repository context assembly helpers."""

from __future__ import annotations

from typing import Any

from ...utils.debug_log import emit_log_call, warning_logger
from ..story_frameworks import summarize_framework_overview
from .common import (
    canonical_repository_ref,
    graph_relationship_types,
    resolve_repository,
)
from .context_infrastructure_support import (
    infrastructure_label_queries,
    infrastructure_query_kwargs,
)
from .framework_summary import build_repository_framework_summary
from .context_limitations import build_context_limitations
from .graph_counts import (
    repository_graph_counts,
    repository_scope,
    repository_scope_predicate,
)
from .relationship_summary import build_relationship_summary

LANGUAGE_BY_EXTENSION = {
    "py": "python",
    "go": "go",
    "js": "javascript",
    "ts": "typescript",
    "rs": "rust",
    "rb": "ruby",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "cs": "csharp",
    "php": "php",
    "ex": "elixir",
    "swift": "swift",
}


def build_repository_context(session: Any, repo_id: str) -> dict[str, Any]:
    """Build the repository context payload for one indexed repository.

    Args:
        session: Database session used for repository queries.
        repo_id: Canonical or fuzzy repository identifier.

    Returns:
        Repository context payload or an error dictionary when the repository is
        missing.
    """

    repo = resolve_repository(session, repo_id)
    if not repo:
        return {"error": f"Repository '{repo_id}' not found"}

    scope = repository_scope(repo)
    repo_ref = canonical_repository_ref(repo)
    relationship_types = graph_relationship_types(session)
    file_stats = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)
        WHERE {repository_scope_predicate()}
        RETURN f.name as file,
               split(f.name, '.')[-1] as ext
        """,
        **scope,
    ).data()

    ext_counts: dict[str, int] = {}
    for file_row in file_stats:
        ext = file_row.get("ext", "")
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    counts = repository_graph_counts(
        session,
        repo,
        relationship_types=relationship_types,
    )
    languages = sorted(
        {
            LANGUAGE_BY_EXTENSION[ext]
            for ext in ext_counts
            if ext in LANGUAGE_BY_EXTENSION
        }
    )

    entry_points = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)
              -[:CONTAINS]->(fn:Function)
        WHERE {repository_scope_predicate()}
          AND (fn.name IN ['main', 'handler', 'lambda_handler',
                           'app', 'run', 'cli', 'entrypoint']
               OR fn.name STARTS WITH 'main')
        RETURN fn.name as name,
               f.relative_path as file,
               fn.line_number as line
        LIMIT 20
        """,
        **scope,
    ).data()

    infrastructure = _fetch_infrastructure(session, repo)
    relationships = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(n1)-[rel]->(n2)
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
        **scope,
    ).data()
    ecosystem = _fetch_ecosystem(session, repo)
    framework_summary = build_repository_framework_summary(session, repo)
    relationship_summary = build_relationship_summary(
        session,
        repo_ref,
        relationship_types=relationship_types,
    )
    coverage_summary = relationship_summary["coverage"]
    if (
        coverage_summary is not None
        and coverage_summary.get("completeness_state") != "complete"
    ):
        emit_log_call(
            warning_logger,
            "Repository context assembled from partial repository coverage",
            event_name="repository.context.partial_coverage",
            extra_keys={
                "repo_id": repo_ref["id"],
                "repo_name": repo_ref["name"],
                "run_id": coverage_summary.get("run_id"),
                "completeness_state": coverage_summary.get("completeness_state"),
                "discovered_file_count": coverage_summary.get("discovered_file_count"),
                "graph_recursive_file_count": coverage_summary.get(
                    "graph_recursive_file_count"
                ),
                "content_file_count": coverage_summary.get("content_file_count"),
                "graph_gap_count": coverage_summary.get("graph_gap_count"),
                "content_gap_count": coverage_summary.get("content_gap_count"),
            },
        )
    repository_payload = {
        **repo_ref,
        "file_count": counts["file_count"],
        "root_file_count": counts["root_file_count"],
        "root_directory_count": counts["root_directory_count"],
        "files_by_extension": ext_counts,
        "graph_available": counts["file_count"] > 0,
        "server_content_available": (
            bool(coverage_summary["server_content_available"])
            if coverage_summary is not None
            else False
        ),
        "active_run_id": (
            coverage_summary["run_id"] if coverage_summary is not None else None
        ),
        "index_status": (
            coverage_summary.get("index_status")
            if coverage_summary is not None
            else None
        ),
    }
    if coverage_summary is not None:
        repository_payload.update(
            {
                "discovered_file_count": coverage_summary.get(
                    "discovered_file_count", 0
                ),
                "graph_recursive_file_count": coverage_summary.get(
                    "graph_recursive_file_count", 0
                ),
                "content_file_count": coverage_summary.get("content_file_count", 0),
                "content_entity_count": coverage_summary.get("content_entity_count", 0),
                "completeness_state": coverage_summary.get(
                    "completeness_state", "failed"
                ),
                "graph_gap_count": coverage_summary.get("graph_gap_count", 0),
                "content_gap_count": coverage_summary.get("content_gap_count", 0),
            }
        )
    limitations = build_context_limitations(
        base_limitations=relationship_summary["limitations"],
        coverage=coverage_summary,
        entry_points=entry_points,
        infrastructure=infrastructure,
        deployment_chain=relationship_summary["deployment_chain"],
        platforms=relationship_summary["platforms"],
    )
    context_payload = {
        "repository": repository_payload,
        "code": {
            "functions": counts["total_function_count"],
            "top_level_functions": counts["top_level_function_count"],
            "class_methods": counts["class_method_count"],
            "classes": counts["class_count"],
            "languages": languages,
            "entry_points": entry_points,
        },
        "coverage": coverage_summary,
        "platforms": relationship_summary["platforms"],
        "deploys_from": relationship_summary["deploys_from"],
        "discovers_config_in": relationship_summary["discovers_config_in"],
        "provisioned_by": relationship_summary["provisioned_by"],
        "provisions_dependencies_for": relationship_summary[
            "provisions_dependencies_for"
        ],
        "iac_relationships": relationship_summary["iac_relationships"],
        "deployment_chain": relationship_summary["deployment_chain"],
        "environments": relationship_summary["environments"],
        "summary": relationship_summary["summary"],
        "limitations": limitations,
        "infrastructure": infrastructure,
        "relationships": relationships,
        "ecosystem": ecosystem,
        "framework_summary": framework_summary,
    }
    framework_story = summarize_framework_overview(framework_summary)
    if framework_story:
        context_payload["framework_story"] = framework_story
    return context_payload


def _fetch_infrastructure(session: Any, repo: dict[str, Any]) -> dict[str, Any]:
    """Collect infrastructure-related repository context sections.

    Args:
        session: Database session used for queries.
        repo: Resolved repository metadata.

    Returns:
        Infrastructure context dictionary with only populated sections.
    """

    infrastructure: dict[str, Any] = {}
    for key, (label, projection) in infrastructure_label_queries().items():
        result = session.run(
            f"""
            MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)
                  -[:CONTAINS]->(n:{label})
            WHERE {repository_scope_predicate()}
            {projection}
            """,
            **repository_scope(repo),
            **infrastructure_query_kwargs(),
        ).data()
        if result:
            infrastructure[key] = result
    direct_runtime_platforms = session.run(
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
        **repository_scope(repo),
    ).data()
    runtime_platforms: list[dict[str, Any]] = []
    if "INSTANCE_OF" in graph_relationship_types(session):
        runtime_platforms = session.run(
            f"""
            MATCH (r:Repository)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[:RUNS_ON]->(p:Platform)
            WHERE {repository_scope_predicate()}
            RETURN DISTINCT p.id as id,
                   p.name as name,
                   p.kind as kind,
                   p.provider as provider,
                   p.environment as environment,
                   i.id as workload_instance_id,
                   i.environment as workload_environment
            ORDER BY p.kind, p.name
            """,
            **repository_scope(repo),
        ).data()
    merged_runtime_platforms = _dedupe_rows(
        [*direct_runtime_platforms, *runtime_platforms]
    )
    if merged_runtime_platforms:
        infrastructure["runtime_platforms"] = merged_runtime_platforms

    provisioned_platforms = session.run(
        f"""
        MATCH (r:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)
        WHERE {repository_scope_predicate()}
        RETURN DISTINCT p.id as id,
               p.name as name,
               p.kind as kind,
               p.provider as provider,
               p.environment as environment
        ORDER BY p.kind, p.name
        """,
        **repository_scope(repo),
    ).data()
    if provisioned_platforms:
        infrastructure["provisioned_platforms"] = provisioned_platforms
    return infrastructure


def _fetch_ecosystem(session: Any, repo: dict[str, Any]) -> dict[str, Any] | None:
    """Collect repository ecosystem metadata for the context payload.

    Args:
        session: Database session used for queries.
        repo: Resolved repository metadata.

    Returns:
        Ecosystem context dictionary when available, otherwise ``None``.
    """

    scope = repository_scope(repo)
    tier = session.run(
        f"""
        MATCH (t:Tier)-[:CONTAINS]->(r:Repository)
        WHERE {repository_scope_predicate()}
        RETURN t.name as tier, t[$risk_level_key] as risk_level
        LIMIT 1
        """,
        **scope,
        risk_level_key="risk_level",
    ).single()
    deps = session.run(
        f"""
        MATCH (r:Repository)-[rel]->(dep:Repository)
        WHERE {repository_scope_predicate()}
          AND type(rel) = $depends_on_type
        RETURN collect(dep.name) as dependencies
        """,
        **scope,
        depends_on_type="DEPENDS_ON",
    ).single()
    dependents = session.run(
        f"""
        MATCH (r:Repository)<-[rel]-(dep:Repository)
        WHERE {repository_scope_predicate()}
          AND type(rel) = $depends_on_type
        RETURN collect(dep.name) as dependents
        """,
        **scope,
        depends_on_type="DEPENDS_ON",
    ).single()
    if not (
        tier
        or (deps and deps["dependencies"])
        or (dependents and dependents["dependents"])
    ):
        return None

    return {
        "tier": tier["tier"] if tier else None,
        "risk_level": tier["risk_level"] if tier else None,
        "dependencies": deps["dependencies"] if deps else [],
        "dependents": dependents["dependents"] if dependents else [],
    }


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
