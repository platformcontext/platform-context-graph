"""Repository-scoped compiled analytics summary helpers."""

from __future__ import annotations

from typing import Any

from .graph_counts import repository_scope, repository_scope_predicate

_DATA_RELATIONSHIP_FIELDS = {
    "COMPILES_TO": "compiles_to",
    "ASSET_DERIVES_FROM": "asset_derives_from",
    "COLUMN_DERIVES_FROM": "column_derives_from",
    "RUNS_QUERY_AGAINST": "runs_query_against",
    "POWERS": "powers",
    "ASSERTS_QUALITY_ON": "asserts_quality_on",
}


def build_repository_data_intelligence_summary(
    session: Any,
    repo: dict[str, Any],
) -> dict[str, Any] | None:
    """Return repository-scoped compiled analytics coverage when present."""

    summary = {
        "analytics_model_count": _count_label(session, repo, "AnalyticsModel"),
        "data_asset_count": _count_label(session, repo, "DataAsset"),
        "data_column_count": _count_label(session, repo, "DataColumn"),
        "query_execution_count": _count_label(session, repo, "QueryExecution"),
        "dashboard_asset_count": _count_label(session, repo, "DashboardAsset"),
        "data_quality_check_count": _count_label(session, repo, "DataQualityCheck"),
        "relationship_counts": _relationship_counts(session, repo),
        "reconciliation": _reconciliation_summary(session, repo),
        "parse_states": _parse_state_counts(session, repo),
        "sample_models": _sample_models(session, repo),
        "sample_queries": _sample_queries(session, repo),
        "sample_dashboards": _sample_dashboards(session, repo),
        "sample_assets": _sample_assets(session, repo),
        "sample_quality_checks": _sample_quality_checks(session, repo),
    }
    if not any(
        (
            summary["analytics_model_count"],
            summary["data_asset_count"],
            summary["data_column_count"],
            summary["query_execution_count"],
            summary["dashboard_asset_count"],
            summary["data_quality_check_count"],
        )
    ):
        return None
    return summary


def _count_label(session: Any, repo: dict[str, Any], label: str) -> int:
    """Count one repository-scoped content entity label."""

    row = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(n:{label})
        WHERE {repository_scope_predicate()}
        RETURN count(DISTINCT n) AS count
        """,
        **repository_scope(repo),
    ).single()
    if row is None:
        return 0
    return int(row.get("count") or 0)


def _relationship_counts(session: Any, repo: dict[str, Any]) -> dict[str, int]:
    """Count repository-scoped compiled analytics lineage edges by type."""

    counts = {field_name: 0 for field_name in _DATA_RELATIONSHIP_FIELDS.values()}
    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(source)
        WHERE {repository_scope_predicate()}
          AND (
            source:AnalyticsModel
            OR source:DataAsset
            OR source:DataColumn
            OR source:QueryExecution
            OR source:DashboardAsset
            OR source:DataQualityCheck
          )
        MATCH (source)-[rel]->()
        WHERE type(rel) IN {list(_DATA_RELATIONSHIP_FIELDS)}
        RETURN type(rel) AS relationship_type,
               count(*) AS count
        """,
        **repository_scope(repo),
    ).data()
    for row in rows:
        relationship_type = str(row.get("relationship_type") or "")
        field_name = _DATA_RELATIONSHIP_FIELDS.get(relationship_type)
        if field_name is None:
            continue
        counts[field_name] = int(row.get("count") or 0)
    return counts


def _parse_state_counts(session: Any, repo: dict[str, Any]) -> dict[str, int]:
    """Return parse-state counts for repository analytics models."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(m:AnalyticsModel)
        WHERE {repository_scope_predicate()}
        RETURN coalesce(m.parse_state, 'unknown') AS parse_state,
               count(*) AS count
        ORDER BY parse_state
        """,
        **repository_scope(repo),
    ).data()
    return {
        str(row.get("parse_state") or "unknown"): int(row.get("count") or 0)
        for row in rows
        if int(row.get("count") or 0) > 0
    }


def _sample_models(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository analytics models."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(m:AnalyticsModel)
        WHERE {repository_scope_predicate()}
        RETURN m.name AS name,
               m.path AS path,
               coalesce(m.parse_state, 'unknown') AS parse_state,
               coalesce(m.confidence, 0.0) AS confidence
        ORDER BY m.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_assets(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository data assets."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(a:DataAsset)
        WHERE {repository_scope_predicate()}
        RETURN a.name AS name,
               coalesce(a.kind, 'asset') AS kind
        ORDER BY a.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_queries(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository query executions."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(q:QueryExecution)
        WHERE {repository_scope_predicate()}
        RETURN q.name AS name,
               coalesce(q.status, 'unknown') AS status,
               coalesce(q.executed_by, '') AS executed_by
        ORDER BY q.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_dashboards(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository dashboard assets."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(d:DashboardAsset)
        WHERE {repository_scope_predicate()}
        RETURN d.name AS name,
               coalesce(d.path, '') AS path,
               coalesce(d.workspace, '') AS workspace
        ORDER BY d.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_quality_checks(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository data-quality checks."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(q:DataQualityCheck)
        WHERE {repository_scope_predicate()}
        RETURN q.name AS name,
               coalesce(q.status, 'unknown') AS status,
               coalesce(q.severity, 'medium') AS severity
        ORDER BY q.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _reconciliation_summary(session: Any, repo: dict[str, Any]) -> dict[str, Any] | None:
    """Return declared-versus-observed asset overlap for one repository."""

    declared_assets = _relationship_target_names(
        session,
        repo,
        source_label="DataAsset",
        relationship_type="ASSET_DERIVES_FROM",
    )
    observed_assets = _relationship_target_names(
        session,
        repo,
        source_label="QueryExecution",
        relationship_type="RUNS_QUERY_AGAINST",
    )
    if not declared_assets and not observed_assets:
        return None

    shared_assets = sorted(declared_assets & observed_assets)
    declared_only_assets = sorted(declared_assets - observed_assets)
    observed_only_assets = sorted(observed_assets - declared_assets)

    if shared_assets and not declared_only_assets and not observed_only_assets:
        status = "aligned"
    elif shared_assets:
        status = "partial_overlap"
    elif declared_only_assets:
        status = "declared_only"
    else:
        status = "observed_only"

    return {
        "status": status,
        "shared_asset_count": len(shared_assets),
        "declared_only_asset_count": len(declared_only_assets),
        "observed_only_asset_count": len(observed_only_assets),
        "shared_assets": shared_assets,
        "declared_only_assets": declared_only_assets,
        "observed_only_assets": observed_only_assets,
    }


def _relationship_target_names(
    session: Any,
    repo: dict[str, Any],
    *,
    source_label: str,
    relationship_type: str,
) -> set[str]:
    """Return distinct target asset names for one repo-scoped relationship type."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(source:{source_label})
        WHERE {repository_scope_predicate()}
        MATCH (source)-[:{relationship_type}]->(target:DataAsset)
        RETURN DISTINCT target.name AS name
        ORDER BY name
        """,
        **repository_scope(repo),
    ).data()
    return {
        str(row.get("name") or "").strip()
        for row in rows
        if str(row.get("name") or "").strip()
    }


__all__ = ["build_repository_data_intelligence_summary"]
