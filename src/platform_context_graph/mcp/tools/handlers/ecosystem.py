"""Ecosystem query handlers for MCP tools."""

from typing import Any

from ....core.database import DatabaseManager
from ....query import infra as infra_queries
from ....query import repositories as repository_queries
from ....query.story_frameworks import summarize_framework_overview
from ....query.story_shared import portable_story_value
from ....utils.debug_log import emit_log_call, warning_logger
from .ecosystem_support import repo_summary_note, trace_deployment_chain
from .ecosystem_support_overview import (
    build_deployment_overview,
    build_story_lines,
)

_BLAST_RADIUS_GRAPH_EVIDENCE_SOURCE = "graph_dependency"
_BLAST_RADIUS_CONSUMER_EVIDENCE_SOURCE = "consumer_reference"


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
            'crossplane_xrd', 'sql_table'.

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
        elif target_type == "sql_table":
            affected = session.run(
                """
                CALL {
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(table)
                    RETURN DISTINCT repo, 0 as hops
                    UNION
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:MIGRATES]->(table)
                    RETURN DISTINCT repo, 1 as hops
                    UNION
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(:Class)-[:MAPS_TO_TABLE]->(table)
                    RETURN DISTINCT repo, 1 as hops
                    UNION
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(:Function)-[:QUERIES_TABLE]->(table)
                    RETURN DISTINCT repo, 1 as hops
                    UNION
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(:SqlTable)-[:REFERENCES_TABLE]->(table)
                    RETURN DISTINCT repo, 1 as hops
                    UNION
                    MATCH (table:SqlTable)
                    WHERE table.name CONTAINS $target_name
                    MATCH (repo:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(sql_node)
                    WHERE (sql_node:SqlView OR sql_node:SqlFunction OR sql_node:SqlTrigger OR sql_node:SqlIndex)
                      AND EXISTS {
                          MATCH (sql_node)-[:READS_FROM|TRIGGERS_ON|INDEXES]->(table)
                      }
                    RETURN DISTINCT repo, 1 as hops
                }
                OPTIONAL MATCH (repo)<-[:CONTAINS]-(tier:Tier)
                RETURN DISTINCT
                    repo.name as repo,
                    repo.id as repo_id,
                    tier.name as tier,
                    tier[$risk_level_key] as risk,
                    hops
                ORDER BY hops, repo
            """,
                target_name=target,
                risk_level_key="risk_level",
            ).data()
        else:
            return {"error": f"Unknown target_type: {target_type}"}

    affected = _normalize_blast_radius_rows(
        affected,
        evidence_source=_BLAST_RADIUS_GRAPH_EVIDENCE_SOURCE,
        inferred=False,
    )
    if target_type == "repository":
        context = repository_queries.get_repository_context(
            db_manager,
            repo_id=target,
        )
        if "error" not in context:
            affected = _merge_consumer_blast_radius_rows(
                affected,
                consumer_repositories=list(context.get("consumer_repositories") or []),
            )

    result: dict[str, Any] = {
        "target": target,
        "target_type": target_type,
        "affected": affected,
        "affected_count": len(affected),
    }
    has_null_tier = any(
        a.get("tier") is None or a.get("risk") is None for a in affected
    )
    if has_null_tier:
        result["note"] = (
            "Tier and risk metadata is absent for some affected repos; "
            "graph dependency and consumer evidence are shown directly."
        )
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
    repo_id: str | None = None,
) -> dict[str, Any]:
    """Get a structured summary of a repository.

    Args:
        db_manager: Database manager.
        repo_id: Canonical repository identifier.

    Returns:
        Summary with files, code entities, infra resources,
        and ecosystem connections.
    """
    if repo_id is None:
        return {"error": "The 'repo_id' argument is required."}
    context = repository_queries.get_repository_context(
        db_manager,
        repo_id=repo_id,
    )
    if "error" in context:
        return context

    repository = context.get("repository") or {}
    ecosystem = context.get("ecosystem") or {}
    coverage = context.get("coverage")
    limitations = list(context.get("limitations") or [])
    summary: dict[str, Any] = {
        "repo_id": repository.get("id"),
        "name": repository.get("name"),
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
        "provisions_dependencies_for": context.get("provisions_dependencies_for", []),
        "environments": context.get("environments", []),
        "observed_config_environments": context.get("observed_config_environments", []),
        "delivery_workflows": context.get("delivery_workflows", {}),
        "delivery_paths": context.get("delivery_paths", []),
        "controller_driven_paths": context.get("controller_driven_paths", []),
        "deployment_artifacts": context.get("deployment_artifacts", {}),
        "consumer_repositories": context.get("consumer_repositories", []),
        "api_surface": context.get("api_surface", {}),
        "hostnames": context.get("hostnames", []),
        "limitations": limitations,
    }
    framework_summary = context.get("framework_summary")
    if framework_summary:
        summary["framework_summary"] = framework_summary
    summary["deployment_overview"] = build_deployment_overview(
        hostnames=summary["hostnames"],
        api_surface=summary["api_surface"],
        platforms=summary["platforms"],
        delivery_paths=summary["delivery_paths"],
        controller_driven_paths=summary["controller_driven_paths"],
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
    framework_story = summarize_framework_overview(framework_summary)
    if framework_story:
        story = [*story, framework_story]
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
    return portable_story_value(summary)


def get_repo_context(
    db_manager: DatabaseManager,
    repo_name: str,
) -> dict[str, Any]:
    """Return canonical repository context for an ecosystem query."""
    return repository_queries.get_repository_context(
        db_manager,
        repo_id=repo_name,
    )


def _normalize_blast_radius_rows(
    rows: list[dict[str, Any]],
    *,
    evidence_source: str,
    inferred: bool,
) -> list[dict[str, Any]]:
    """Return blast-radius rows with stable evidence metadata attached."""

    normalized: list[dict[str, Any]] = []
    for row in rows:
        repo_name = str(row.get("repo") or "").strip()
        if not repo_name:
            continue
        row_copy = dict(row)
        row_copy["repo"] = repo_name
        row_copy["tier"] = row_copy.get("tier")
        row_copy["risk"] = row_copy.get("risk")
        row_copy["hops"] = row_copy.get("hops")
        row_copy["evidence_source"] = evidence_source
        row_copy["inferred"] = inferred
        normalized.append(row_copy)
    return normalized


def _merge_consumer_blast_radius_rows(
    affected: list[dict[str, Any]],
    *,
    consumer_repositories: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Add consumer-repository evidence without duplicating graph rows."""

    seen = {
        str(row.get("repo") or "").strip()
        for row in affected
        if str(row.get("repo") or "").strip()
    }
    merged = list(affected)
    for row in consumer_repositories:
        if not isinstance(row, dict):
            continue
        repo_name = str(row.get("repository") or row.get("name") or "").strip()
        if not repo_name or repo_name in seen:
            continue
        seen.add(repo_name)
        merged.append(
            {
                "repo": repo_name,
                "repo_id": row.get("repo_id"),
                "tier": None,
                "risk": None,
                "hops": None,
                "evidence_source": _BLAST_RADIUS_CONSUMER_EVIDENCE_SOURCE,
                "evidence_kinds": list(row.get("evidence_kinds") or []),
                "matched_values": list(row.get("matched_values") or []),
                "sample_paths": list(row.get("sample_paths") or []),
                "inferred": True,
            }
        )
    return merged
