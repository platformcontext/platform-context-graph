"""Ecosystem query handlers for MCP tools.

Provides high-level ecosystem queries that return structured
data from the graph: overview, deployment traces, blast radius,
resource search, and relationship analysis.
"""

from typing import Any

from ....core.database import DatabaseManager
from ....query import infra as infra_queries
from ....query import repositories as repository_queries
from ....utils.debug_log import emit_log_call, warning_logger


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


def get_ecosystem_overview(
    db_manager: DatabaseManager,
) -> dict[str, Any]:
    """Return a high-level infrastructure overview from the query layer."""
    return infra_queries.get_ecosystem_overview(db_manager)


def trace_deployment_chain(
    db_manager: DatabaseManager,
    service_name: str,
) -> dict[str, Any]:
    """Trace the full deployment chain for a service.

    Follows repository-backed and ApplicationSet-backed deployment
    paths through ArgoCD, then surfaces the related Kubernetes and
    infrastructure resources.

    Args:
        db_manager: Database manager.
        service_name: Name of the repo/service to trace.

    Returns:
        Structured chain from source to infrastructure.
    """
    context = repository_queries.get_repository_context(
        db_manager,
        repo_id=service_name,
    )
    if "error" in context:
        return context

    canonical_repository = context.get("repository") or {}
    canonical_name = str(canonical_repository.get("name") or service_name)
    driver = db_manager.get_driver()

    with driver.session() as session:
        # Find the repo
        repo = session.run(
            "MATCH (r:Repository) "
            "WHERE r.name CONTAINS $name "
            "RETURN r.name as name, r.path as path "
            "LIMIT 1",
            name=canonical_name,
        ).single()

        if not repo:
            repo = {
                "name": canonical_name,
                "path": canonical_repository.get("local_path")
                or canonical_repository.get("path"),
            }

        # ArgoCD applications sourcing from this repo
        argocd_apps = session.run(
            """
            MATCH (app:ArgoCDApplication)-[:SOURCES_FROM]->(r:Repository)
            WHERE r.name CONTAINS $name
            RETURN app.name as app_name,
                   app[$project_key] as project,
                   app[$dest_namespace_key] as namespace,
                   app[$source_path_key] as source_path
        """,
            name=canonical_name,
            project_key="project",
            dest_namespace_key="dest_namespace",
            source_path_key="source_path",
        ).data()

        argocd_appsets = session.run(
            """
            MATCH (app:ArgoCDApplicationSet)
            WHERE app.name CONTAINS $name
               OR EXISTS {
                    MATCH (app)-[:SOURCES_FROM]->(r:Repository)
                    WHERE r.name CONTAINS $name
               }
            RETURN app.name as app_name,
                   app[$project_key] as project,
                   app.namespace as namespace,
                   app[$dest_namespace_key] as dest_namespace,
                   app[$source_repos_key] as source_repos,
                   app[$source_paths_key] as source_paths,
                   app[$source_roots_key] as source_roots
        """,
            name=canonical_name,
            project_key="project",
            dest_namespace_key="dest_namespace",
            source_repos_key="source_repos",
            source_paths_key="source_paths",
            source_roots_key="source_roots",
        ).data()

        # K8s resources in the repo
        repo_k8s_resources = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(k:K8sResource)
            WHERE r.name CONTAINS $name
            RETURN k.name as name, k.kind as kind,
                   k.namespace as namespace,
                   f.relative_path as file
        """,
            name=canonical_name,
        ).data()

        deployed_k8s_resources = session.run(
            """
            MATCH (app)-[:DEPLOYS]->(k:K8sResource)
            WHERE (app:ArgoCDApplication AND EXISTS {
                        MATCH (app)-[:SOURCES_FROM]->(r:Repository)
                        WHERE r.name CONTAINS $name
                  })
               OR (app:ArgoCDApplicationSet AND (
                        app.name CONTAINS $name
                        OR EXISTS {
                            MATCH (app)-[:SOURCES_FROM]->(r:Repository)
                            WHERE r.name CONTAINS $name
                        }
                  ))
            MATCH (f:File)-[:CONTAINS]->(k)
            MATCH (repo:Repository)-[:CONTAINS*]->(f)
            RETURN DISTINCT
                   k.name as name,
                   k.kind as kind,
                   k.namespace as namespace,
                   f.relative_path as file,
                   repo.name as repository,
                   app.name as deployed_by
        """,
            name=canonical_name,
        ).data()

        # Crossplane claims in the repo
        claims = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(claim:CrossplaneClaim)
            WHERE r.name CONTAINS $name
            OPTIONAL MATCH (claim)-[:SATISFIED_BY]->(xrd:CrossplaneXRD)
            OPTIONAL MATCH (xrd)-[:IMPLEMENTED_BY]->(comp:CrossplaneComposition)
            RETURN claim.name as claim_name,
                   claim.kind as claim_kind,
                   xrd.kind as xrd_kind,
                   xrd.group as xrd_group,
                   comp.name as composition_name
        """,
            name=canonical_name,
        ).data()

        # Terraform resources in the repo
        terraform = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(tf:TerraformResource)
            WHERE r.name CONTAINS $name
            RETURN tf.name as name,
                   tf.resource_type as resource_type,
                   f.relative_path as file
        """,
            name=canonical_name,
        ).data()

        # Terraform modules used
        tf_modules = session.run(
            """
            MATCH (r:Repository)-[:CONTAINS*]->(f:File)-[:CONTAINS]->(mod:TerraformModule)
            WHERE r.name CONTAINS $name
            RETURN mod.name as name,
                   mod.source as source,
                   mod.version as version
        """,
            name=canonical_name,
        ).data()

    k8s_resources = _dedupe_rows(repo_k8s_resources + deployed_k8s_resources)

    limitations = list(context.get("limitations") or [])
    result = {
        "repository": dict(repo),
        "argocd_applications": argocd_apps,
        "argocd_applicationsets": argocd_appsets,
        "k8s_resources": k8s_resources,
        "crossplane_claims": claims,
        "terraform_resources": terraform,
        "terraform_modules": tf_modules,
        "coverage": context.get("coverage"),
        "platforms": context.get("platforms", []),
        "deploys_from": context.get("deploys_from", []),
        "discovers_config_in": context.get("discovers_config_in", []),
        "provisioned_by": context.get("provisioned_by", []),
        "provisions_dependencies_for": context.get(
            "provisions_dependencies_for", []
        ),
        "deployment_chain": context.get("deployment_chain", []),
        "environments": context.get("environments", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    if limitations:
        result["note"] = _repo_summary_note(
            limitations=limitations,
            coverage=context.get("coverage"),
        )
        emit_log_call(
            warning_logger,
            "Deployment chain assembled with known limitations",
            event_name="deployment.chain.limitations",
            extra_keys={
                "repo_name": canonical_name,
                "limitations": limitations,
                "platform_count": len(result["platforms"]),
                "deployment_chain_length": len(result["deployment_chain"]),
            },
        )
    return result


def find_blast_radius(
    db_manager: DatabaseManager,
    target: str,
    target_type: str = "repository",
) -> dict[str, Any]:
    """Find all repos/resources affected by changing a target.

    Uses graph traversal to find transitive dependents.

    Args:
        db_manager: Database manager.
        target: Name of the target (repo, module, XRD).
        target_type: One of 'repository', 'terraform_module',
            'crossplane_xrd'.

    Returns:
        Affected repos with hop counts and tier info.
    """
    driver = db_manager.get_driver()

    with driver.session() as session:
        if target_type == "repository":
            affected = session.run(
                """
                MATCH (source:Repository)
                WHERE source.name CONTAINS $target_name
                OPTIONAL MATCH path = (source)<-[rels*1..5]-(affected:Repository)
                WHERE all(rel IN rels WHERE type(rel) = $depends_on_type)
                OPTIONAL MATCH (affected)<-[:CONTAINS]-(tier:Tier)
                RETURN DISTINCT
                    affected.name as repo,
                    tier.name as tier,
                    tier[$risk_level_key] as risk,
                    length(path) as hops
                ORDER BY hops
            """,
                target_name=target,
                depends_on_type="DEPENDS_ON",
                risk_level_key="risk_level",
            ).data()

        elif target_type == "terraform_module":
            affected = session.run(
                """
                MATCH (mod:TerraformModule)
                WHERE mod.name CONTAINS $target_name
                   OR mod.source CONTAINS $target_name
                MATCH (f:File)-[:CONTAINS]->(mod)
                MATCH (repo:Repository)-[:CONTAINS*]->(f)
                OPTIONAL MATCH path = (repo)<-[rels*0..5]-(affected:Repository)
                WHERE all(rel IN rels WHERE type(rel) = $depends_on_type)
                OPTIONAL MATCH (affected)<-[:CONTAINS]-(tier:Tier)
                RETURN DISTINCT
                    affected.name as repo,
                    tier.name as tier,
                    tier[$risk_level_key] as risk
            """,
                target_name=target,
                depends_on_type="DEPENDS_ON",
                risk_level_key="risk_level",
            ).data()

        elif target_type == "crossplane_xrd":
            affected = session.run(
                """
                MATCH (xrd:CrossplaneXRD)
                WHERE xrd.kind CONTAINS $target_name
                   OR xrd.name CONTAINS $target_name
                OPTIONAL MATCH (claim:CrossplaneClaim)-[:SATISFIED_BY]->(xrd)
                MATCH (f:File)-[:CONTAINS]->(claim)
                MATCH (repo:Repository)-[:CONTAINS*]->(f)
                OPTIONAL MATCH (affected)<-[:CONTAINS]-(tier:Tier)
                RETURN DISTINCT
                    repo.name as repo,
                    tier.name as tier,
                    claim.name as claim
            """,
                target_name=target,
            ).data()
        else:
            return {"error": f"Unknown target_type: {target_type}"}

    result: dict[str, Any] = {
        "target": target,
        "target_type": target_type,
        "affected": affected,
        "affected_count": len(affected),
    }
    has_null_tier = any(
        a.get("tier") is None or a.get("risk") is None
        for a in affected
        if a.get("repo") is not None
    )
    if has_null_tier:
        result["note"] = "Tier and risk levels require an ecosystem manifest."
    return result


def find_infra_resources(
    db_manager: DatabaseManager,
    query: str,
    category: str = "",
) -> dict[str, Any]:
    """Search infrastructure resources by query and optional category."""
    return infra_queries.search_infra_resources(
        db_manager,
        query=query,
        types=[category] if category else None,
        limit=50,
    )


def analyze_infra_relationships(
    db_manager: DatabaseManager,
    query_type: str,
    target: str,
) -> dict[str, Any]:
    """Return infrastructure relationships for a target resource."""
    return infra_queries.get_infra_relationships(
        db_manager,
        target=target,
        relationship_type=query_type,
    )


def get_repo_summary(
    db_manager: DatabaseManager,
    repo_name: str,
) -> dict[str, Any]:
    """Get a structured summary of a repository.

    Args:
        db_manager: Database manager.
        repo_name: Name of the repository.

    Returns:
        Summary with files, code entities, infra resources,
        and ecosystem connections.
    """
    context = repository_queries.get_repository_context(
        db_manager,
        repo_id=repo_name,
    )
    if "error" in context:
        return context

    repository = context.get("repository") or {}
    ecosystem = context.get("ecosystem") or {}
    coverage = context.get("coverage")
    limitations = list(context.get("limitations") or [])
    summary: dict[str, Any] = {
        "name": repository.get("name"),
        "path": repository.get("local_path") or repository.get("path"),
        "file_count": repository.get("discovered_file_count")
        or repository.get("file_count")
        or 0,
        "files_by_extension": repository.get("files_by_extension", {}),
        "code": context.get("code", {}),
        "infrastructure": context.get("infrastructure", {}),
        "dependencies": ecosystem.get("dependencies", []),
        "dependents": ecosystem.get("dependents", []),
        "coverage": coverage,
        "platforms": context.get("platforms", []),
        "deploys_from": context.get("deploys_from", []),
        "discovers_config_in": context.get("discovers_config_in", []),
        "provisioned_by": context.get("provisioned_by", []),
        "provisions_dependencies_for": context.get(
            "provisions_dependencies_for", []
        ),
        "environments": context.get("environments", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    if limitations:
        summary["note"] = _repo_summary_note(limitations=limitations, coverage=coverage)
        emit_log_call(
            warning_logger,
            "Repository summary assembled with known limitations",
            event_name="repository.summary.limitations",
            extra_keys={
                "repo_name": summary.get("name"),
                "limitations": limitations,
                "platform_count": len(summary["platforms"]),
                "environment_count": len(summary["environments"]),
            },
        )
    if ecosystem.get("tier") is not None or ecosystem.get("risk_level") is not None:
        summary["tier"] = {
            "tier": ecosystem.get("tier"),
            "risk_level": ecosystem.get("risk_level"),
        }
    return summary


def _repo_summary_note(
    *, limitations: list[str], coverage: dict[str, Any] | None
) -> str:
    """Return a short human-readable note for limitation codes."""

    if "graph_partial" in limitations or "content_partial" in limitations:
        return "Repository coverage is partial; graph/content counts may be incomplete."
    if "dns_unknown" in limitations and "entrypoint_unknown" in limitations:
        return "DNS and entrypoint evidence are currently unavailable for this repository."
    if "dns_unknown" in limitations:
        return "DNS evidence is currently unavailable for this repository."
    if "entrypoint_unknown" in limitations:
        return "Entrypoint evidence is currently unavailable for this repository."
    if coverage and coverage.get("completeness_state") == "failed":
        return "Repository coverage failed; runtime and deployment summaries may be incomplete."
    return "Repository context has known limitations."


def get_repo_context(
    db_manager: DatabaseManager,
    repo_name: str,
) -> dict[str, Any]:
    """Return canonical repository context for an ecosystem query."""
    return repository_queries.get_repository_context(
        db_manager,
        repo_id=repo_name,
    )
