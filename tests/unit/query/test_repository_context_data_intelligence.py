"""Data-intelligence coverage for repository context responses."""

from __future__ import annotations

import pytest

from platform_context_graph.query.repositories.context_data import (
    build_repository_context,
)
from platform_context_graph.query.repositories.context_data_intelligence import (
    _sample_models,
)


class _Result:
    """Minimal query result wrapper for repository-context tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, object]]:
        return self._rows


class _Session:
    """Minimal session stub returning empty query results."""

    def run(self, _query: str, **_kwargs: object) -> _Result:
        return _Result([])


class _AnalyticsModelSampleSession:
    """Minimal session stub for analytics-model sample query assertions."""

    def run(self, query: str, **_kwargs: object) -> _Result:
        assert "coalesce(m.unresolved_reference_count, 0) AS unresolved_reference_count" in query
        assert "coalesce(m.unresolved_reference_reasons, []) AS unresolved_reference_reasons" in query
        assert (
            "coalesce(m.unresolved_reference_expressions, []) AS unresolved_reference_expressions"
            in query
        )
        assert (
            "ORDER BY CASE coalesce(m.parse_state, 'unknown') WHEN 'partial' THEN 0 ELSE 1 END,"
            in query
        )
        return _Result(
            [
                {
                    "name": "orders_expanded",
                    "path": (
                        "target/compiled/jaffle_shop/models/marts/orders_expanded.sql"
                    ),
                    "parse_state": "partial",
                    "confidence": 0.5,
                    "materialization": "table",
                    "unresolved_reference_count": 1,
                    "unresolved_reference_reasons": [
                        "wildcard_projection_not_supported"
                    ],
                    "unresolved_reference_expressions": ["o.*"],
                },
                {
                    "name": "order_metrics",
                    "path": "target/compiled/jaffle_shop/models/marts/order_metrics.sql",
                    "parse_state": "complete",
                    "confidence": 1.0,
                    "materialization": "view",
                    "unresolved_reference_count": 0,
                    "unresolved_reference_reasons": [],
                    "unresolved_reference_expressions": [],
                },
            ]
        )


def test_build_repository_context_adds_data_intelligence_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository context should surface compiled analytics coverage."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda *_args, **_kwargs: {
            "id": "repository:r_demo",
            "name": "analytics-warehouse",
            "path": "/repos/analytics-warehouse",
            "local_path": "/repos/analytics-warehouse",
            "remote_url": "https://github.com/platformcontext/analytics-warehouse",
            "repo_slug": "platformcontext/analytics-warehouse",
            "has_remote": True,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.graph_relationship_types",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda *_args, **_kwargs: {
            "root_file_count": 0,
            "root_directory_count": 0,
            "file_count": 1,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_relationship_summary",
        lambda *_args, **_kwargs: {
            "coverage": None,
            "limitations": [],
            "platforms": [],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "provisions_dependencies_for": [],
            "iac_relationships": [],
            "deployment_chain": [],
            "environments": [],
            "summary": {},
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_repository_framework_summary",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_data_intelligence",
        lambda *_args, **_kwargs: {
            "analytics_model_count": 2,
            "data_asset_count": 5,
            "data_column_count": 10,
            "query_execution_count": 2,
            "dashboard_asset_count": 1,
            "data_quality_check_count": 1,
            "relationship_counts": {
                "compiles_to": 2,
                "asset_derives_from": 5,
                "column_derives_from": 4,
                "runs_query_against": 4,
                "powers": 3,
                "asserts_quality_on": 1,
            },
            "reconciliation": {
                "status": "partial_overlap",
                "shared_asset_count": 2,
                "declared_only_asset_count": 1,
                "observed_only_asset_count": 1,
                "shared_assets": [
                    "raw.public.customers",
                    "raw.public.orders",
                ],
                "declared_only_assets": ["raw.public.payments"],
                "observed_only_assets": ["raw.public.refunds"],
            },
            "parse_states": {"complete": 1, "partial": 1},
            "sample_models": [
                {
                    "name": "order_metrics",
                    "path": "target/compiled/jaffle_shop/models/marts/order_metrics.sql",
                    "parse_state": "complete",
                },
                {
                    "name": "orders_expanded",
                    "path": (
                        "target/compiled/jaffle_shop/models/marts/orders_expanded.sql"
                    ),
                    "parse_state": "partial",
                },
            ],
            "sample_dashboards": [
                {
                    "name": "Revenue Overview",
                    "path": "dashboards/revenue_overview.json",
                    "workspace": "finance",
                }
            ],
            "sample_assets": [
                {"name": "analytics.public.order_metrics", "kind": "model"},
                {"name": "raw.public.orders", "kind": "source"},
            ],
            "sample_quality_checks": [
                {
                    "name": "gross_amount_non_negative",
                    "status": "failing",
                    "severity": "high",
                }
            ],
        },
        raising=False,
    )

    result = build_repository_context(_Session(), "analytics-warehouse")

    assert result["data_intelligence"]["analytics_model_count"] == 2
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 2,
        "asset_derives_from": 5,
        "column_derives_from": 4,
        "runs_query_against": 4,
        "powers": 3,
        "asserts_quality_on": 1,
    }
    assert result["data_intelligence"]["query_execution_count"] == 2
    assert result["data_intelligence"]["dashboard_asset_count"] == 1
    assert result["data_intelligence"]["data_quality_check_count"] == 1
    assert result["data_intelligence"]["reconciliation"] == {
        "status": "partial_overlap",
        "shared_asset_count": 2,
        "declared_only_asset_count": 1,
        "observed_only_asset_count": 1,
        "shared_assets": [
            "raw.public.customers",
            "raw.public.orders",
        ],
        "declared_only_assets": ["raw.public.payments"],
        "observed_only_assets": ["raw.public.refunds"],
    }
    assert result["data_intelligence"]["parse_states"] == {
        "complete": 1,
        "partial": 1,
    }
    assert [
        item["name"] for item in result["data_intelligence"]["sample_models"]
    ] == [
        "order_metrics",
        "orders_expanded",
    ]


def test_sample_models_prioritizes_partial_models_and_gap_fields() -> None:
    """Repository sample models should surface unresolved-gap details first."""

    result = _sample_models(
        _AnalyticsModelSampleSession(),
        {"id": "repository:r_demo", "name": "analytics-warehouse"},
    )

    assert result[0] == {
        "name": "orders_expanded",
        "path": "target/compiled/jaffle_shop/models/marts/orders_expanded.sql",
        "parse_state": "partial",
        "confidence": 0.5,
        "materialization": "table",
        "unresolved_reference_count": 1,
        "unresolved_reference_reasons": ["wildcard_projection_not_supported"],
        "unresolved_reference_expressions": ["o.*"],
    }


def test_build_repository_context_handles_semantic_and_dashboard_only_repos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository context should summarize semantic assets without models."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda *_args, **_kwargs: {
            "id": "repository:r_semantic_demo",
            "name": "semantic-replay-comprehensive",
            "path": "/repos/semantic-replay-comprehensive",
            "local_path": "/repos/semantic-replay-comprehensive",
            "remote_url": "https://github.com/platformcontext/semantic-replay-comprehensive",
            "repo_slug": "platformcontext/semantic-replay-comprehensive",
            "has_remote": True,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.graph_relationship_types",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda *_args, **_kwargs: {
            "root_file_count": 0,
            "root_directory_count": 0,
            "file_count": 1,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_relationship_summary",
        lambda *_args, **_kwargs: {
            "coverage": None,
            "limitations": [],
            "platforms": [],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "provisions_dependencies_for": [],
            "iac_relationships": [],
            "deployment_chain": [],
            "environments": [],
            "summary": {},
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_repository_framework_summary",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_data_intelligence",
        lambda *_args, **_kwargs: {
            "analytics_model_count": 0,
            "data_asset_count": 3,
            "data_column_count": 5,
            "query_execution_count": 1,
            "dashboard_asset_count": 1,
            "data_quality_check_count": 0,
            "relationship_counts": {
                "compiles_to": 0,
                "asset_derives_from": 1,
                "column_derives_from": 2,
                "runs_query_against": 1,
                "powers": 2,
                "asserts_quality_on": 0,
            },
            "reconciliation": {
                "status": "aligned",
                "shared_asset_count": 1,
                "declared_only_asset_count": 0,
                "observed_only_asset_count": 0,
                "shared_assets": ["analytics.finance.daily_revenue"],
                "declared_only_assets": [],
                "observed_only_assets": [],
            },
            "parse_states": {},
            "sample_models": [],
            "sample_queries": [
                {
                    "name": "semantic_revenue_lookup",
                    "status": "success",
                    "executed_by": "semantic_cache_refresh",
                }
            ],
            "sample_dashboards": [
                {
                    "name": "Semantic Revenue Overview",
                    "path": "dashboards/semantic_revenue_overview.json",
                    "workspace": "finance",
                }
            ],
            "sample_assets": [
                {"name": "semantic.finance.revenue_semantic", "kind": "semantic_model"},
                {"name": "analytics.finance.daily_revenue", "kind": "table"},
            ],
            "sample_quality_checks": [],
        },
        raising=False,
    )

    result = build_repository_context(_Session(), "semantic-replay-comprehensive")

    assert result["data_intelligence"]["analytics_model_count"] == 0
    assert result["data_intelligence"]["relationship_counts"] == {
        "compiles_to": 0,
        "asset_derives_from": 1,
        "column_derives_from": 2,
        "runs_query_against": 1,
        "powers": 2,
        "asserts_quality_on": 0,
    }
    assert result["data_intelligence"]["dashboard_asset_count"] == 1


def test_build_repository_context_surfaces_quality_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository context should surface quality-check counts and samples."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda *_args, **_kwargs: {
            "id": "repository:r_quality_demo",
            "name": "quality-replay-comprehensive",
            "path": "/repos/quality-replay-comprehensive",
            "local_path": "/repos/quality-replay-comprehensive",
            "remote_url": "https://github.com/platformcontext/quality-replay-comprehensive",
            "repo_slug": "platformcontext/quality-replay-comprehensive",
            "has_remote": True,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.graph_relationship_types",
        lambda *_args, **_kwargs: set(),
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.repository_graph_counts",
        lambda *_args, **_kwargs: {
            "root_file_count": 0,
            "root_directory_count": 0,
            "file_count": 1,
            "top_level_function_count": 0,
            "class_method_count": 0,
            "total_function_count": 0,
            "class_count": 0,
            "module_count": 0,
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_infrastructure",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_ecosystem",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_relationship_summary",
        lambda *_args, **_kwargs: {
            "coverage": None,
            "limitations": [],
            "platforms": [],
            "deploys_from": [],
            "discovers_config_in": [],
            "provisioned_by": [],
            "provisions_dependencies_for": [],
            "iac_relationships": [],
            "deployment_chain": [],
            "environments": [],
            "summary": {},
        },
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.build_repository_framework_summary",
        lambda *_args, **_kwargs: {},
    )
    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data._fetch_data_intelligence",
        lambda *_args, **_kwargs: {
            "analytics_model_count": 0,
            "data_asset_count": 1,
            "data_column_count": 2,
            "query_execution_count": 1,
            "dashboard_asset_count": 0,
            "data_quality_check_count": 2,
            "relationship_counts": {
                "compiles_to": 0,
                "asset_derives_from": 0,
                "column_derives_from": 0,
                "runs_query_against": 1,
                "powers": 0,
                "asserts_quality_on": 2,
            },
            "reconciliation": None,
            "parse_states": {},
            "sample_models": [],
            "sample_queries": [],
            "sample_dashboards": [],
            "sample_assets": [
                {"name": "analytics.finance.daily_revenue", "kind": "table"},
            ],
            "sample_quality_checks": [
                {
                    "name": "daily_revenue_freshness",
                    "status": "passing",
                    "severity": "medium",
                },
                {
                    "name": "gross_amount_non_negative",
                    "status": "failing",
                    "severity": "high",
                },
            ],
        },
        raising=False,
    )

    result = build_repository_context(_Session(), "quality-replay-comprehensive")

    assert result["data_intelligence"]["data_quality_check_count"] == 2
    assert result["data_intelligence"]["relationship_counts"]["asserts_quality_on"] == 2
    assert [
        item["name"] for item in result["data_intelligence"]["sample_quality_checks"]
    ] == ["daily_revenue_freshness", "gross_amount_non_negative"]
