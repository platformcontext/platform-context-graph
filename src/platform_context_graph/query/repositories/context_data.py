"""Repository context assembly helpers."""

from __future__ import annotations

from typing import Any

from ...repository_identity import build_repo_access
from .common import canonical_repository_ref, resolve_repository

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

    scope = _repository_scope(repo)
    repo_ref = canonical_repository_ref(repo)
    file_stats = session.run(
        f"""
        MATCH (r:Repository)-[:CONTAINS*]->(f:File)
        WHERE {_repository_scope_predicate()}
        RETURN f.name as file,
               split(f.name, '.')[-1] as ext
        """,
        **scope,
    ).data()

    ext_counts: dict[str, int] = {}
    for file_row in file_stats:
        ext = file_row.get("ext", "")
        ext_counts[ext] = ext_counts.get(ext, 0) + 1

    code_stats = session.run(
        f"""
        MATCH (r:Repository)-[:CONTAINS*]->(f:File)
        WHERE {_repository_scope_predicate()}
        OPTIONAL MATCH (f)-[:CONTAINS]->(fn:Function)
        OPTIONAL MATCH (f)-[:CONTAINS]->(cls:Class)
        RETURN count(DISTINCT fn) as functions,
               count(DISTINCT cls) as classes
        """,
        **scope,
    ).single()
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
        WHERE {_repository_scope_predicate()}
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
        WHERE {_repository_scope_predicate()}
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
    return {
        "repository": {
            **repo_ref,
            "file_count": len(file_stats),
            "files_by_extension": ext_counts,
            "repo_access": build_repo_access(repo_ref),
        },
        "code": {
            "functions": code_stats["functions"] if code_stats else 0,
            "classes": code_stats["classes"] if code_stats else 0,
            "languages": languages,
            "entry_points": entry_points,
        },
        "infrastructure": infrastructure,
        "relationships": relationships,
        "ecosystem": ecosystem,
    }


def _repository_scope(repo: dict[str, Any]) -> dict[str, Any]:
    """Build parameters that scope follow-up queries to one repository node."""

    return {
        "repo_id": repo.get("id"),
        "repo_path": repo.get("local_path") or repo.get("path"),
    }


def _repository_scope_predicate() -> str:
    """Return the shared Cypher predicate for scoping one repository."""

    return (
        "(($repo_id IS NOT NULL AND r.id = $repo_id) "
        "OR ($repo_path IS NOT NULL AND coalesce(r.local_path, r.path) = $repo_path))"
    )


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
                   n.default as default
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
            RETURN n.name as name, n.project as project,
                   n.dest_namespace as dest_namespace,
                   n.source_repo as source_repo
            """,
        ),
        "argocd_applicationsets": (
            "ArgoCDApplicationSet",
            """
            RETURN n.name as name,
                   n.generators as generators,
                   n.project as project,
                   n.dest_namespace as dest_namespace,
                   n.source_repos as source_repos,
                   n.source_paths as source_paths
            """,
        ),
        "crossplane_xrds": (
            "CrossplaneXRD",
            """
            RETURN n.name as name, n.kind as kind,
                   n.claim_kind as claim_kind
            """,
        ),
        "crossplane_compositions": (
            "CrossplaneComposition",
            """
            RETURN n.name as name,
                   n.composite_kind as composite_kind
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
                   n.terraform_source as terraform_source
            """,
        ),
    }
    infrastructure: dict[str, Any] = {}
    for key, (label, projection) in label_queries.items():
        result = session.run(
            f"""
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)
                  -[:CONTAINS]->(n:{label})
            WHERE {_repository_scope_predicate()}
            {projection}
            """,
            **_repository_scope(repo),
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

    scope = _repository_scope(repo)
    tier = session.run(
        f"""
        MATCH (t:Tier)-[:CONTAINS]->(r:Repository)
        WHERE {_repository_scope_predicate()}
        RETURN t.name as tier, t.risk_level as risk_level
        LIMIT 1
        """,
        **scope,
    ).single()
    deps = session.run(
        f"""
        MATCH (r:Repository)-[:DEPENDS_ON]->(dep:Repository)
        WHERE {_repository_scope_predicate()}
        RETURN collect(dep.name) as dependencies
        """,
        **scope,
    ).single()
    dependents = session.run(
        f"""
        MATCH (r:Repository)<-[:DEPENDS_ON]-(dep:Repository)
        WHERE {_repository_scope_predicate()}
        RETURN collect(dep.name) as dependents
        """,
        **scope,
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
