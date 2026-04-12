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
    "OWNS": "owns",
    "DECLARES_CONTRACT_FOR": "declares_contract_for",
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
        "data_owner_count": _count_label(session, repo, "DataOwner"),
        "data_contract_count": _count_label(session, repo, "DataContract"),
        "protected_column_count": _count_protected_columns(session, repo),
        "relationship_counts": _relationship_counts(session, repo),
        "reconciliation": _reconciliation_summary(session, repo),
        "observed_usage_summary": _observed_usage_summary(session, repo),
        "lineage_gap_summary": _lineage_gap_summary(session, repo),
        "parse_states": _parse_state_counts(session, repo),
        "sample_models": _sample_models(session, repo),
        "sample_queries": _sample_queries(session, repo),
        "sample_dashboards": _sample_dashboards(session, repo),
        "sample_assets": _sample_assets(session, repo),
        "sample_quality_checks": _sample_quality_checks(session, repo),
        "sample_owners": _sample_owners(session, repo),
        "sample_contracts": _sample_contracts(session, repo),
        "sample_protected_columns": _sample_protected_columns(session, repo),
    }
    if not any(
        (
            summary["analytics_model_count"],
            summary["data_asset_count"],
            summary["data_column_count"],
            summary["query_execution_count"],
            summary["dashboard_asset_count"],
            summary["data_quality_check_count"],
            summary["data_owner_count"],
            summary["data_contract_count"],
            summary["protected_column_count"],
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
            OR source:DataOwner
            OR source:DataContract
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


def _lineage_gap_summary(session: Any, repo: dict[str, Any]) -> dict[str, Any] | None:
    """Return aggregated unresolved-lineage details for partial analytics models."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(m:AnalyticsModel)
        WHERE {repository_scope_predicate()}
          AND coalesce(m.parse_state, 'unknown') = 'partial'
        RETURN m.name AS name,
               coalesce(m.unresolved_reference_reasons, []) AS reasons,
               coalesce(m.unresolved_reference_expressions, []) AS expressions
        ORDER BY m.name
        """,
        **repository_scope(repo),
    ).data()
    if not rows:
        return None

    reason_counts: dict[str, int] = {}
    sample_models: list[str] = []
    sample_expressions: list[str] = []
    seen_expressions: set[str] = set()

    for row in rows:
        model_name = str(row.get("name") or "").strip()
        if model_name:
            sample_models.append(model_name)
        for reason in row.get("reasons") or []:
            normalized_reason = str(reason or "").strip()
            if not normalized_reason:
                continue
            reason_counts[normalized_reason] = reason_counts.get(normalized_reason, 0) + 1
        for expression in row.get("expressions") or []:
            normalized_expression = str(expression or "").strip()
            if (
                not normalized_expression
                or normalized_expression in seen_expressions
            ):
                continue
            seen_expressions.add(normalized_expression)
            sample_expressions.append(normalized_expression)

    sorted_reason_counts = {
        reason: count
        for reason, count in sorted(
            reason_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    }
    return {
        "partial_model_count": len(rows),
        "reason_counts": sorted_reason_counts,
        "sample_models": sample_models[:5],
        "sample_expressions": sample_expressions[:5],
    }


def _sample_models(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository analytics models."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(m:AnalyticsModel)
        WHERE {repository_scope_predicate()}
        RETURN m.name AS name,
               coalesce(m.compiled_path, m.path) AS path,
               coalesce(m.parse_state, 'unknown') AS parse_state,
               coalesce(m.confidence, 0.0) AS confidence,
               coalesce(m.materialization, 'unknown') AS materialization,
               coalesce(m.unresolved_reference_count, 0) AS unresolved_reference_count,
               coalesce(m.unresolved_reference_reasons, []) AS unresolved_reference_reasons,
               coalesce(m.unresolved_reference_expressions, []) AS unresolved_reference_expressions
        ORDER BY CASE coalesce(m.parse_state, 'unknown') WHEN 'partial' THEN 0 ELSE 1 END,
                 m.name
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


def _count_protected_columns(session: Any, repo: dict[str, Any]) -> int:
    """Count repository-scoped protected data columns."""

    row = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(c:DataColumn)
        WHERE {repository_scope_predicate()}
          AND c.is_protected = true
        RETURN count(DISTINCT c) AS count
        """,
        **repository_scope(repo),
    ).single()
    if row is None:
        return 0
    return int(row.get("count") or 0)


def _sample_owners(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository data owners."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(o:DataOwner)
        WHERE {repository_scope_predicate()}
        RETURN o.name AS name,
               coalesce(o.team, '') AS team
        ORDER BY o.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_contracts(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of repository data contracts."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(c:DataContract)
        WHERE {repository_scope_predicate()}
        RETURN c.name AS name,
               coalesce(c.contract_level, 'unspecified') AS contract_level,
               coalesce(c.change_policy, 'unknown') AS change_policy
        ORDER BY c.name
        LIMIT 5
        """,
        **repository_scope(repo),
    ).data()


def _sample_protected_columns(session: Any, repo: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a compact ordered sample of protected repository data columns."""

    return session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(c:DataColumn)
        WHERE {repository_scope_predicate()}
          AND c.is_protected = true
        RETURN c.name AS name,
               coalesce(c.sensitivity, '') AS sensitivity,
               coalesce(c.protection_kind, '') AS protection_kind
        ORDER BY c.name
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


def _observed_usage_summary(session: Any, repo: dict[str, Any]) -> dict[str, Any] | None:
    """Return replay-derived hot and low-use asset signals for one repository."""

    rows = session.run(
        f"""
        MATCH (r:Repository)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(q:QueryExecution)
        WHERE {repository_scope_predicate()}
        MATCH (q)-[:RUNS_QUERY_AGAINST]->(asset:DataAsset)
        RETURN asset.name AS name,
               count(DISTINCT q) AS query_count
        ORDER BY query_count DESC, name
        """,
        **repository_scope(repo),
    ).data()
    usage_rows = [
        {
            "name": str(row.get("name") or "").strip(),
            "query_count": int(row.get("query_count") or 0),
        }
        for row in rows
        if str(row.get("name") or "").strip() and int(row.get("query_count") or 0) > 0
    ]
    if not usage_rows:
        return None

    hot_assets = [row for row in usage_rows if row["query_count"] >= 2]
    low_use_assets = [row for row in usage_rows if row["query_count"] == 1]
    return {
        "hot_asset_count": len(hot_assets),
        "low_use_asset_count": len(low_use_assets),
        "max_query_count": max(row["query_count"] for row in usage_rows),
        "hot_assets": hot_assets[:5],
        "low_use_assets": low_use_assets[:5],
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
