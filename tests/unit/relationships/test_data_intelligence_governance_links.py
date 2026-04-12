"""Unit tests for governance replay relationship materialization."""

from __future__ import annotations

from unittest.mock import Mock

from platform_context_graph.relationships.data_intelligence_links import (
    create_all_data_intelligence_links,
)


def test_create_all_data_intelligence_links_materializes_governance_edges() -> None:
    """Governance payloads should emit owner, contract, and overlay writes."""

    session = Mock()
    file_data = [
        {
            "path": "/tmp/analytics/governance_replay.json",
            "data_assets": [
                {
                    "name": "analytics.finance.daily_revenue",
                    "uid": "content-entity:e_asset_daily_revenue",
                    "line_number": 1,
                }
            ],
            "data_columns": [
                {
                    "name": "analytics.finance.daily_revenue.customer_email",
                    "uid": "content-entity:e_column_customer_email",
                    "line_number": 1,
                }
            ],
            "data_owners": [
                {
                    "name": "Finance Analytics",
                    "uid": "content-entity:e_owner_finance_analytics",
                    "line_number": 1,
                }
            ],
            "data_contracts": [
                {
                    "name": "daily_revenue_contract",
                    "uid": "content-entity:e_contract_daily_revenue",
                    "line_number": 1,
                }
            ],
            "data_relationships": [
                {
                    "type": "OWNS",
                    "source_name": "Finance Analytics",
                    "target_name": "analytics.finance.daily_revenue",
                    "line_number": 1,
                },
                {
                    "type": "DECLARES_CONTRACT_FOR",
                    "source_name": "daily_revenue_contract",
                    "target_name": "analytics.finance.daily_revenue.customer_email",
                    "line_number": 1,
                },
            ],
            "data_governance_annotations": [
                {
                    "target_name": "analytics.finance.daily_revenue.customer_email",
                    "target_kind": "DataColumn",
                    "owner_names": ["Finance Analytics"],
                    "owner_teams": ["finance-analytics"],
                    "contract_names": ["daily_revenue_contract"],
                    "contract_levels": ["gold"],
                    "change_policies": ["breaking"],
                    "sensitivity": "pii",
                    "is_protected": True,
                    "protection_kind": "masked",
                }
            ],
        }
    ]

    metrics = create_all_data_intelligence_links(session, file_data)

    assert metrics == {
        "declares_contract_for_edges": 1,
        "governance_annotations_applied": 1,
        "owns_edges": 1,
    }
    assert session.run.call_count == 3

