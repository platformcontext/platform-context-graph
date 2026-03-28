"""Infrastructure-oriented query helpers for the HTTP and MCP surfaces."""

from __future__ import annotations

from typing import Any, Sequence

from ..core.records import record_to_dict as _record_to_dict
from ..observability import trace_query

__all__ = [
    "search_infra_resources",
    "get_infra_relationships",
    "get_ecosystem_overview",
]


def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return rows with duplicates removed while preserving order."""

    seen: set[tuple[tuple[str, str], ...]] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = tuple(sorted((str(key), repr(value)) for key, value in row.items()))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _row_identity(row: dict[str, Any]) -> tuple[str, str, str, str]:
    """Return a stable identity tuple for infra search rows."""

    return (
        str(row.get("name") or ""),
        str(row.get("kind") or ""),
        str(row.get("namespace") or ""),
        str(row.get("file") or ""),
    )


def search_infra_resources(
    database: Any,
    *,
    query: str,
    types: Sequence[str] | None = None,
    environment: str | None = None,
    limit: int = 10,
) -> dict[str, Any]:
    """Search infrastructure resources across supported infra categories."""
    with trace_query("infra_search"):
        driver = database.get_driver()
        results: dict[str, list] = {}
        requested_categories = list(types or [])
        categories = set(requested_categories)

        def enabled(category: str) -> bool:
            """Return whether one infra category should be queried."""
            return not categories or category in categories

        with driver.session() as session:
            if enabled("k8s"):
                results["k8s_resources"] = session.run(
                    """
                MATCH (k:K8sResource)
                WHERE k.name CONTAINS $search
                   OR k.kind CONTAINS $search
                MATCH (f:File)-[:CONTAINS]->(k)
                RETURN k.name as name, k.kind as kind,
                       k.namespace as namespace,
                       f.relative_path as file
                LIMIT 50
            """,
                    search=query,
                ).data()[:limit]

            if enabled("terraform"):
                results["terraform_resources"] = session.run(
                    """
                MATCH (t:TerraformResource)
                WHERE t.name CONTAINS $search
                   OR t.resource_type CONTAINS $search
                MATCH (f:File)-[:CONTAINS]->(t)
                RETURN t.name as name,
                       t.resource_type as type,
                       f.relative_path as file
                LIMIT 50
            """,
                    search=query,
                ).data()[:limit]

            if enabled("argocd"):
                results["argocd_applications"] = session.run(
                    """
                MATCH (a:ArgoCDApplication)
                WHERE a.name CONTAINS $search
                RETURN a.name as name,
                       a[$project_key] as project,
                       a[$dest_namespace_key] as namespace,
                       a[$source_repo_key] as source_repo
                LIMIT 50
            """,
                    search=query,
                    project_key="project",
                    dest_namespace_key="dest_namespace",
                    source_repo_key="source_repo",
                ).data()[:limit]
                results["argocd_applicationsets"] = session.run(
                    """
                MATCH (a:ArgoCDApplicationSet)
                WHERE a.name CONTAINS $search
                   OR coalesce(a[$source_paths_key], '') CONTAINS $search
                   OR coalesce(a[$source_roots_key], '') CONTAINS $search
                MATCH (f:File)-[:CONTAINS]->(a)
                OPTIONAL MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                RETURN a.name as name,
                       a[$project_key] as project,
                       a.namespace as namespace,
                       a[$dest_namespace_key] as dest_namespace,
                       repo.name as repository,
                       f.relative_path as file
                LIMIT 50
            """,
                    search=query,
                    project_key="project",
                    dest_namespace_key="dest_namespace",
                    source_paths_key="source_paths",
                    source_roots_key="source_roots",
                ).data()[:limit]

            if enabled("crossplane"):
                results["crossplane_xrds"] = session.run(
                    """
                MATCH (x:CrossplaneXRD)
                WHERE x.name CONTAINS $search
                   OR x.kind CONTAINS $search
                RETURN x.name as name, x.kind as kind,
                       x.group as api_group,
                       x[$claim_kind_key] as claim_kind
                LIMIT 50
            """,
                    search=query,
                    claim_kind_key="claim_kind",
                ).data()[:limit]
                stored_claims = session.run(
                    """
                MATCH (c:CrossplaneClaim)
                WHERE c.name CONTAINS $search
                   OR c.kind CONTAINS $search
                MATCH (f:File)-[:CONTAINS]->(c)
                OPTIONAL MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                RETURN c.name as name, c.kind as kind,
                       c.namespace as namespace,
                       c.api_version as api_version,
                       repo.name as repository,
                       f.relative_path as file
                LIMIT 50
            """,
                    search=query,
                ).data()
                k8s_claim_fallback = session.run(
                    """
                MATCH (k:K8sResource)
                WHERE k.name CONTAINS $search
                   OR k.kind CONTAINS $search
                MATCH (f:File)-[:CONTAINS]->(k)
                OPTIONAL MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                WITH k, f, repo, split(coalesce(k.api_version, ''), '/')[0] as api_group
                MATCH (x:CrossplaneXRD)
                WHERE x.kind = k.kind
                   OR x[$claim_kind_key] = k.kind
                   OR x.group = api_group
                RETURN DISTINCT
                       k.name as name,
                       k.kind as kind,
                       k.namespace as namespace,
                       k.api_version as api_version,
                       repo.name as repository,
                       f.relative_path as file
                LIMIT 50
            """,
                    search=query,
                    claim_kind_key="claim_kind",
                ).data()
                results["crossplane_claims"] = _dedupe_rows(
                    stored_claims + k8s_claim_fallback
                )[:limit]
                claim_keys = {
                    _row_identity(row) for row in results["crossplane_claims"]
                }
                if claim_keys and results.get("k8s_resources"):
                    results["k8s_resources"] = [
                        row
                        for row in results["k8s_resources"]
                        if _row_identity(row) not in claim_keys
                    ]

            if enabled("helm"):
                results["helm_charts"] = session.run(
                    """
                MATCH (h:HelmChart)
                WHERE h.name CONTAINS $search
                RETURN h.name as name,
                       h.version as version,
                       h.app_version as app_version
                LIMIT 50
            """,
                    search=query,
                ).data()[:limit]

        category = requested_categories[0] if len(requested_categories) == 1 else ""
        return {"query": query, "category": category, "results": results}


def get_infra_relationships(
    database: Any,
    *,
    target: str,
    relationship_type: str | None = None,
    environment: str | None = None,
) -> dict[str, Any]:
    """Return relationship views for one infrastructure target."""
    with trace_query("infra_relationships"):
        if not relationship_type:
            return {"error": "relationship_type is required"}

        driver = database.get_driver()

        with driver.session() as session:
            if relationship_type == "what_deploys":
                data = session.run(
                    """
                MATCH (app:ArgoCDApplication)-[:DEPLOYS]->(k:K8sResource)
                WHERE k.name CONTAINS $target_name
                   OR app.name CONTAINS $target_name
                RETURN app.name as app_name,
                       k.name as resource_name,
                       k.kind as resource_kind,
                       k.namespace as namespace
            """,
                    target_name=target,
                ).data()
            elif relationship_type == "what_provisions":
                data = session.run(
                    """
                MATCH (claim:CrossplaneClaim)-[:SATISFIED_BY]->(xrd:CrossplaneXRD)
                WHERE claim.name CONTAINS $target_name
                OPTIONAL MATCH (xrd)-[:IMPLEMENTED_BY]->(comp:CrossplaneComposition)
                RETURN claim.name as claim,
                       xrd.kind as xrd_kind,
                       comp.name as composition
            """,
                    target_name=target,
                ).data()
            elif relationship_type == "who_consumes_xrd":
                data = session.run(
                    """
                MATCH (xrd:CrossplaneXRD)
                WHERE xrd.kind CONTAINS $target_name
                   OR xrd.name CONTAINS $target_name
                MATCH (claim:CrossplaneClaim)-[:SATISFIED_BY]->(xrd)
                MATCH (f:File)-[:CONTAINS]->(claim)
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                RETURN DISTINCT
                    repo.name as repo,
                    claim.name as claim,
                    f.relative_path as file
            """,
                    target_name=target,
                ).data()
            elif relationship_type == "module_consumers":
                data = session.run(
                    """
                MATCH (mod:TerraformModule)
                WHERE mod.name CONTAINS $target_name
                   OR mod.source CONTAINS $target_name
                MATCH (f:File)-[:CONTAINS]->(mod)
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
                RETURN DISTINCT
                    repo.name as repo,
                    mod.name as module_name,
                    mod.source as source,
                    f.relative_path as file
            """,
                    target_name=target,
                ).data()
            else:
                return {"error": f"Unknown query_type: {relationship_type}"}

        return {
            "query_type": relationship_type,
            "target": target,
            "results": data,
            "count": len(data),
        }


def get_ecosystem_overview(database: Any) -> dict[str, Any]:
    """Return ecosystem-wide repository and infrastructure summary data."""
    with trace_query("ecosystem_overview"):
        driver = database.get_driver()

        with driver.session() as session:
            eco_result = session.run("""
            OPTIONAL MATCH (e:Ecosystem)
            RETURN e.name as name, e.org as org
            LIMIT 1
        """).single()

            tiers = session.run(
                """
            MATCH (t:Tier)
            OPTIONAL MATCH (t)-[:CONTAINS]->(r:Repository)
            RETURN t.name as tier,
                   t[$risk_level_key] as risk,
                   collect(r.name) as repos
            ORDER BY CASE t[$risk_level_key]
                         WHEN 'critical' THEN 4
                         WHEN 'high' THEN 3
                         WHEN 'medium' THEN 2
                         WHEN 'low' THEN 1
                         ELSE 0
                     END DESC
        """,
                risk_level_key="risk_level",
            ).data()

            repo_stats = session.run(
                """
            MATCH (r:Repository)
            OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
            OPTIONAL MATCH (r)-[rel]->(dep:Repository)
            WHERE dep IS NULL OR type(rel) = $depends_on_type
            RETURN r.name as name,
                   r.path as path,
                   count(DISTINCT f) as files,
                   collect(DISTINCT dep.name) as depends_on
            ORDER BY r.name
        """,
                depends_on_type="DEPENDS_ON",
            ).data()

            infra_counts = session.run("""
            OPTIONAL MATCH (k:K8sResource) WITH count(k) as k8s
            OPTIONAL MATCH (a:ArgoCDApplication) WITH k8s, count(a) as argocd
            OPTIONAL MATCH (x:CrossplaneXRD) WITH k8s, argocd, count(x) as xrds
            OPTIONAL MATCH (t:TerraformResource) WITH k8s, argocd, xrds, count(t) as terraform
            OPTIONAL MATCH (h:HelmChart) WITH k8s, argocd, xrds, terraform, count(h) as helm
            RETURN k8s, argocd, xrds, terraform, helm
        """).single()

            rel_counts = session.run(
                """
            OPTIONAL MATCH ()-[s:SOURCES_FROM]->() WITH count(s) as sources_from
            OPTIONAL MATCH ()-[d:DEPLOYS]->() WITH sources_from, count(d) as deploys
            OPTIONAL MATCH ()-[sat:SATISFIED_BY]->() WITH sources_from, deploys, count(sat) as satisfied_by
            OPTIONAL MATCH ()-[dep]->()
            WHERE type(dep) = $depends_on_type
            WITH sources_from, deploys, satisfied_by, count(dep) as depends_on
            RETURN sources_from, deploys, satisfied_by, depends_on
        """,
                depends_on_type="DEPENDS_ON",
            ).single()

        eco_name = eco_result["name"] if eco_result else None
        eco_org = eco_result["org"] if eco_result else None
        result: dict[str, Any] = {
            "tiers": tiers,
            "repos": repo_stats,
            "infrastructure_counts": _record_to_dict(infra_counts),
            "cross_repo_relationships": _record_to_dict(rel_counts),
        }
        if eco_name:
            result["ecosystem"] = {"name": eco_name, "org": eco_org}
        else:
            result["mode"] = "standalone"
            result["note"] = "No ecosystem manifest. Showing all indexed repositories."
        return result
