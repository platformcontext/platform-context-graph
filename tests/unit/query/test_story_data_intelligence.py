"""Focused story overview tests for compiled analytics responses."""

from __future__ import annotations

from platform_context_graph.query.story import build_repository_story_response


def test_repository_story_exposes_data_intelligence_section() -> None:
    """Repository stories should summarize compiled analytics coverage."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_analytics_warehouse",
                "name": "analytics-warehouse",
                "repo_slug": "platformcontext/analytics-warehouse",
                "remote_url": (
                    "https://github.com/platformcontext/analytics-warehouse"
                ),
                "has_remote": True,
            },
            "code": {"functions": 0, "classes": 0, "class_methods": 0},
            "data_intelligence": {
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
                    "masks": 0,
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
                "lineage_gap_summary": {
                    "partial_model_count": 1,
                    "reason_counts": {
                        "wildcard_projection_not_supported": 1,
                    },
                    "sample_models": ["orders_expanded"],
                    "sample_expressions": ["o.*"],
                },
                "parse_states": {"complete": 1, "partial": 1},
                "sample_models": [
                    {
                        "name": "order_metrics",
                        "path": (
                            "target/compiled/jaffle_shop/models/marts/order_metrics.sql"
                        ),
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
            "limitations": [],
        }
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert data_section["summary"] == (
        "Compiled analytics covers 2 models, 5 data assets, 10 data columns, 2 warehouse queries, 1 dashboard, and 1 quality check; "
        "declared and observed lineage overlap on 2 assets, with 1 declared-only and 1 observed-only asset; "
        "lineage is partial for 1 model because wildcard projection not supported remains unresolved (for example o.*)."
    )
    assert [item["name"] for item in data_section["items"]] == [
        "order_metrics",
        "orders_expanded",
    ]
    assert result["data_intelligence_overview"]["parse_states"] == {
        "complete": 1,
        "partial": 1,
    }
    assert result["data_intelligence_overview"]["reconciliation"]["status"] == (
        "partial_overlap"
    )


def test_repository_story_uses_dashboards_when_semantic_repo_has_no_models() -> None:
    """Repository stories should fall back to dashboard examples for semantic repos."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_semantic_demo",
                "name": "semantic-replay-comprehensive",
                "repo_slug": "platformcontext/semantic-replay-comprehensive",
                "remote_url": (
                    "https://github.com/platformcontext/semantic-replay-comprehensive"
                ),
                "has_remote": True,
            },
            "code": {"functions": 0, "classes": 0, "class_methods": 0},
            "data_intelligence": {
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
                    "masks": 0,
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
            "limitations": [],
        }
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "1 dashboard" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "Semantic Revenue Overview"
    ]


def test_repository_story_mentions_observed_hot_and_low_use_assets() -> None:
    """Repository stories should summarize replay hot spots and low-use assets."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_warehouse_demo",
                "name": "warehouse-replay-comprehensive",
                "repo_slug": "platformcontext/warehouse-replay-comprehensive",
                "remote_url": (
                    "https://github.com/platformcontext/warehouse-replay-comprehensive"
                ),
                "has_remote": True,
            },
            "code": {"functions": 0, "classes": 0, "class_methods": 0},
            "data_intelligence": {
                "analytics_model_count": 0,
                "data_asset_count": 3,
                "data_column_count": 7,
                "query_execution_count": 2,
                "dashboard_asset_count": 0,
                "data_quality_check_count": 0,
                "relationship_counts": {
                    "compiles_to": 0,
                    "asset_derives_from": 0,
                    "column_derives_from": 0,
                    "runs_query_against": 4,
                    "powers": 0,
                    "asserts_quality_on": 0,
                    "masks": 0,
                },
                "reconciliation": None,
                "observed_usage_summary": {
                    "hot_asset_count": 1,
                    "low_use_asset_count": 2,
                    "max_query_count": 2,
                    "hot_assets": [
                        {
                            "name": "analytics.finance.daily_revenue",
                            "query_count": 2,
                        }
                    ],
                    "low_use_assets": [
                        {
                            "name": "analytics.crm.customers",
                            "query_count": 1,
                        },
                        {
                            "name": "analytics.finance.revenue",
                            "query_count": 1,
                        },
                    ],
                },
                "parse_states": {},
                "sample_models": [],
                "sample_queries": [
                    {
                        "name": "daily_revenue_build",
                        "status": "success",
                        "executed_by": "etl_runner",
                    },
                    {
                        "name": "revenue_dashboard_lookup",
                        "status": "success",
                        "executed_by": "bi_reader",
                    },
                ],
                "sample_dashboards": [],
                "sample_assets": [
                    {"name": "analytics.finance.daily_revenue", "kind": "table"},
                    {"name": "analytics.crm.customers", "kind": "table"},
                ],
                "sample_quality_checks": [],
            },
            "limitations": [],
        }
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "observed hot assets include analytics.finance.daily_revenue (2 queries)" in (
        data_section["summary"]
    )
    assert "observed low-use assets include analytics.crm.customers, analytics.finance.revenue" in (
        data_section["summary"]
    )


def test_repository_story_uses_quality_checks_when_no_models_or_dashboards() -> None:
    """Repository stories should fall back to quality checks for quality fixtures."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_quality_demo",
                "name": "quality-replay-comprehensive",
                "repo_slug": "platformcontext/quality-replay-comprehensive",
                "remote_url": (
                    "https://github.com/platformcontext/quality-replay-comprehensive"
                ),
                "has_remote": True,
            },
            "code": {"functions": 0, "classes": 0, "class_methods": 0},
            "data_intelligence": {
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
                    "masks": 0,
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
            "limitations": [],
        }
    )

    data_section = next(
        section
        for section in result["story_sections"]
        if section["id"] == "data_intelligence"
    )
    assert "2 quality checks" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "daily_revenue_freshness",
        "gross_amount_non_negative",
    ]
