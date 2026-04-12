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
                "relationship_counts": {
                    "compiles_to": 2,
                    "asset_derives_from": 5,
                    "column_derives_from": 4,
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
                "sample_assets": [
                    {"name": "analytics.public.order_metrics", "kind": "model"},
                    {"name": "raw.public.orders", "kind": "source"},
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
        "Compiled analytics covers 2 models, 5 data assets, and 10 data columns; "
        "lineage is partial for 1 model."
    )
    assert [item["name"] for item in data_section["items"]] == [
        "order_metrics",
        "orders_expanded",
    ]
    assert result["data_intelligence_overview"]["parse_states"] == {
        "complete": 1,
        "partial": 1,
    }
