"""Ecosystem query handlers for MCP tools."""

from typing import Any

from ....core.database import DatabaseManager
from ....query import infra as infra_queries
from ....query import repositories as repository_queries
from ....utils.debug_log import emit_log_call, warning_logger
from .ecosystem_support import repo_summary_note, trace_deployment_chain
from .ecosystem_support_overview import (
    build_deployment_overview,
    build_story_lines,
)


def get_ecosystem_overview(
    db_manager: DatabaseManager,
) -> dict[str, Any]:
    """Return a high-level infrastructure overview from the query layer."""
    return infra_queries.get_ecosystem_overview(db_manager)


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
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
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
                MATCH (repo:Repository)-[:REPO_CONTAINS]->(f)
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
        "observed_config_environments": context.get(
            "observed_config_environments", []
        ),
        "delivery_workflows": context.get("delivery_workflows", {}),
        "delivery_paths": context.get("delivery_paths", []),
        "deployment_artifacts": context.get("deployment_artifacts", {}),
        "consumer_repositories": context.get("consumer_repositories", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    summary["deployment_overview"] = build_deployment_overview(
        hostnames=summary["hostnames"],
        api_surface=summary["api_surface"],
        platforms=summary["platforms"],
        delivery_paths=summary["delivery_paths"],
        deployment_artifacts=summary["deployment_artifacts"],
        consumer_repositories=summary["consumer_repositories"],
    )
    note = repo_summary_note(
        limitations=limitations,
        coverage=coverage,
        environments=summary["environments"],
        observed_config_environments=summary["observed_config_environments"],
    )
    if note:
        summary["note"] = note
    story = build_story_lines(
        deployment_overview=summary["deployment_overview"],
        note=summary.get("note", ""),
    )
    if story:
        summary["story"] = story
    if limitations:
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


def get_repo_context(
    db_manager: DatabaseManager,
    repo_name: str,
) -> dict[str, Any]:
    """Return canonical repository context for an ecosystem query."""
    return repository_queries.get_repository_context(
        db_manager,
        repo_id=repo_name,
    )
