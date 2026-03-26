"""Repository context assembly helpers."""

from __future__ import annotations

from typing import Any

from ...runtime.status_store import get_repository_coverage as get_runtime_repository_coverage
from .common import canonical_repository_ref, resolve_repository
from .coverage_data import coverage_summary_from_row
from .graph_counts import repository_graph_counts, repository_scope, repository_scope_predicate

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
    file_stats = session.run(
        f"""
        MATCH (r:Repository)-[:CONTAINS*]->(f:File)
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

    counts = repository_graph_counts(session, repo)
    languages = sorted(
        {
            LANGUAGE_BY_EXTENSION[ext]
            for ext in ext_counts
            if ext in LANGUAGE_BY_EXTENSION
        }
    )

    entry_points = session.run(
        f"""
        MATCH (r:Repository)-[:CONTAINS*]->(f:File)
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
        **scope,
    ).data()
    ecosystem = _fetch_ecosystem(session, repo)
    coverage_summary = coverage_summary_from_row(
        get_runtime_repository_coverage(repo_id=repo_ref["id"])
    )
    return {
        "repository": {
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
                coverage_summary["index_status"]
                if coverage_summary is not None
                else None
            ),
        },
        "code": {
            "functions": counts["total_function_count"],
            "top_level_functions": counts["top_level_function_count"],
            "class_methods": counts["class_method_count"],
            "classes": counts["class_count"],
            "languages": languages,
            "entry_points": entry_points,
        },
        "coverage": coverage_summary,
        "infrastructure": infrastructure,
        "relationships": relationships,
        "ecosystem": ecosystem,
    }


def _fetch_infrastructure(session: Any, repo: dict[str, Any]) -> dict[str, Any]:
    """Collect infrastructure-related repository context sections.

    Args:
        session: Database session used for queries.
        repo: Resolved repository metadata.

    Returns:
        Infrastructure context dictionary with only populated sections.
    """

    label_queries = {
        "k8s_resources": (
            "K8sResource",
            """
            RETURN n.name as name, n.kind as kind,
                   n.namespace as namespace,
                   f.relative_path as file
            """,
        ),
        "terraform_resources": (
            "TerraformResource",
            """
            RETURN n.name as name,
                   n.resource_type as resource_type,
                   f.relative_path as file
            """,
        ),
        "terraform_modules": (
            "TerraformModule",
            """
            RETURN n.name as name,
                   n.source as source,
                   n.version as version
            """,
        ),
        "terraform_variables": (
            "TerraformVariable",
            """
            RETURN n.name as name,
                   n.description as description,
                   n[$default_key] as default
            """,
        ),
        "terraform_outputs": (
            "TerraformOutput",
            """
            RETURN n.name as name,
                   n.description as description
            """,
        ),
        "argocd_applications": (
            "ArgoCDApplication",
            """
            RETURN n.name as name, n[$project_key] as project,
                   n[$dest_namespace_key] as dest_namespace,
                   n[$source_repo_key] as source_repo
            """,
        ),
        "argocd_applicationsets": (
            "ArgoCDApplicationSet",
            """
            RETURN n.name as name,
                   n[$generators_key] as generators,
                   n[$project_key] as project,
                   n[$dest_namespace_key] as dest_namespace,
                   n[$source_repos_key] as source_repos,
                   n[$source_paths_key] as source_paths
            """,
        ),
        "crossplane_xrds": (
            "CrossplaneXRD",
            """
            RETURN n.name as name, n.kind as kind,
                   n[$claim_kind_key] as claim_kind
            """,
        ),
        "crossplane_compositions": (
            "CrossplaneComposition",
            """
            RETURN n.name as name,
                   n[$composite_kind_key] as composite_kind
            """,
        ),
        "crossplane_claims": (
            "CrossplaneClaim",
            """
            RETURN n.name as name, n.kind as kind,
                   n.namespace as namespace
            """,
        ),
        "helm_charts": (
            "HelmChart",
            """
            RETURN n.name as name, n.version as version,
                   n.app_version as app_version
            """,
        ),
        "helm_values": (
            "HelmValues",
            """
            RETURN n.name as name,
                   n.top_level_keys as top_level_keys
            """,
        ),
        "kustomize_overlays": (
            "KustomizeOverlay",
            """
            RETURN n.name as name, n.namespace as namespace,
                   n.resources as resources
            """,
        ),
        "terragrunt_configs": (
            "TerragruntConfig",
            """
            RETURN n.name as name,
                   n[$terraform_source_key] as terraform_source
            """,
        ),
    }
    infrastructure: dict[str, Any] = {}
    for key, (label, projection) in label_queries.items():
        result = session.run(
            f"""
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)
                  -[:CONTAINS]->(n:{label})
            WHERE {repository_scope_predicate()}
            {projection}
            """,
            **repository_scope(repo),
            default_key="default",
            project_key="project",
            dest_namespace_key="dest_namespace",
            generators_key="generators",
            source_repo_key="source_repo",
            source_repos_key="source_repos",
            source_paths_key="source_paths",
            claim_kind_key="claim_kind",
            composite_kind_key="composite_kind",
            terraform_source_key="terraform_source",
        ).data()
        if result:
            infrastructure[key] = result
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
