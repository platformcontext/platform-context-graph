"""Story coverage for governance overlays."""

from __future__ import annotations

from platform_context_graph.query.story import build_repository_story_response


def test_repository_story_mentions_governance_overlay_coverage() -> None:
    """Repository stories should summarize owners, contracts, and protection."""

    result = build_repository_story_response(
        {
            "repository": {
                "id": "repository:r_governance_demo",
                "name": "governance-replay-comprehensive",
                "repo_slug": "platformcontext/governance-replay-comprehensive",
                "remote_url": (
                    "https://github.com/platformcontext/governance-replay-comprehensive"
                ),
                "has_remote": True,
            },
            "code": {"functions": 0, "classes": 0, "class_methods": 0},
            "data_intelligence": {
                "analytics_model_count": 0,
                "data_asset_count": 1,
                "data_column_count": 3,
                "query_execution_count": 1,
                "dashboard_asset_count": 0,
                "data_quality_check_count": 0,
                "data_owner_count": 1,
                "data_contract_count": 1,
                "protected_column_count": 1,
                "relationship_counts": {
                    "compiles_to": 0,
                    "asset_derives_from": 0,
                    "column_derives_from": 0,
                    "runs_query_against": 1,
                    "powers": 0,
                    "asserts_quality_on": 0,
                    "owns": 2,
                    "declares_contract_for": 3,
                    "masks": 1,
                },
                "reconciliation": None,
                "parse_states": {},
                "sample_models": [],
                "sample_queries": [],
                "sample_dashboards": [],
                "sample_assets": [
                    {"name": "analytics.finance.daily_revenue", "kind": "table"},
                ],
                "sample_quality_checks": [],
                "sample_owners": [
                    {"name": "Finance Analytics", "team": "finance-analytics"}
                ],
                "sample_contracts": [
                    {
                        "name": "daily_revenue_contract",
                        "contract_level": "gold",
                        "change_policy": "breaking",
                    }
                ],
                "sample_protected_columns": [
                    {
                        "name": "analytics.finance.daily_revenue.customer_email",
                        "sensitivity": "pii",
                        "protection_kind": "masked",
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
    assert "1 owner" in data_section["summary"]
    assert "1 contract" in data_section["summary"]
    assert "1 protected column" in data_section["summary"]
    assert [item["name"] for item in data_section["items"]] == [
        "daily_revenue_contract"
    ]
