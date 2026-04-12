"""Unit tests for data-intelligence relationship materialization."""

from __future__ import annotations

from unittest.mock import Mock

from platform_context_graph.relationships.data_intelligence_links import (
    create_all_data_intelligence_links,
)


def test_create_all_data_intelligence_links_materializes_compiled_lineage() -> None:
    """Compiled analytics payloads should emit graph lineage edges."""

    session = Mock()
    file_data = [
        {
            "path": "/tmp/analytics/target/manifest.json",
            "analytics_models": [
                {
                    "name": "order_metrics",
                    "uid": "content-entity:e_model_order_metrics",
                    "line_number": 1,
                }
            ],
            "data_assets": [
                {
                    "name": "analytics.public.order_metrics",
                    "uid": "content-entity:e_asset_order_metrics",
                    "line_number": 1,
                },
                {
                    "name": "raw.public.orders",
                    "uid": "content-entity:e_asset_orders",
                    "line_number": 1,
                },
            ],
            "data_columns": [
                {
                    "name": "analytics.public.order_metrics.order_id",
                    "uid": "content-entity:e_column_order_id",
                    "line_number": 1,
                },
                {
                    "name": "raw.public.orders.id",
                    "uid": "content-entity:e_column_orders_id",
                    "line_number": 1,
                },
            ],
            "query_executions": [
                {
                    "name": "daily_revenue_build",
                    "uid": "content-entity:e_query_daily_revenue_build",
                    "line_number": 1,
                }
            ],
            "dashboard_assets": [
                {
                    "name": "Revenue Overview",
                    "uid": "content-entity:e_dashboard_revenue_overview",
                    "line_number": 1,
                }
            ],
            "data_relationships": [
                {
                    "type": "COMPILES_TO",
                    "source_name": "order_metrics",
                    "target_name": "analytics.public.order_metrics",
                    "line_number": 1,
                },
                {
                    "type": "ASSET_DERIVES_FROM",
                    "source_name": "analytics.public.order_metrics",
                    "target_name": "raw.public.orders",
                    "line_number": 1,
                },
                {
                    "type": "COLUMN_DERIVES_FROM",
                    "source_name": "analytics.public.order_metrics.order_id",
                    "target_name": "raw.public.orders.id",
                    "line_number": 1,
                },
                {
                    "type": "RUNS_QUERY_AGAINST",
                    "source_name": "daily_revenue_build",
                    "target_name": "raw.public.orders",
                    "line_number": 1,
                },
                {
                    "type": "POWERS",
                    "source_name": "analytics.public.order_metrics",
                    "target_name": "Revenue Overview",
                    "line_number": 1,
                },
            ],
        }
    ]

    metrics = create_all_data_intelligence_links(session, file_data)

    assert metrics == {
        "asset_derives_from_edges": 1,
        "column_derives_from_edges": 1,
        "compiles_to_edges": 1,
        "powers_edges": 1,
        "runs_query_against_edges": 1,
    }
    assert session.run.call_count == 5
