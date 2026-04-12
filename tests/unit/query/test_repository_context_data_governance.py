"""Repository-context coverage for governance overlays."""

from __future__ import annotations

import pytest

from platform_context_graph.query.repositories.context_data import (
    build_repository_context,
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


def test_build_repository_context_surfaces_governance_overlay_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repository context should summarize owner, contract, and protected data."""

    monkeypatch.setattr(
        "platform_context_graph.query.repositories.context_data.resolve_repository",
        lambda *_args, **_kwargs: {
            "id": "repository:r_governance_demo",
            "name": "governance-replay-comprehensive",
            "path": "/repos/governance-replay-comprehensive",
            "local_path": "/repos/governance-replay-comprehensive",
            "remote_url": (
                "https://github.com/platformcontext/governance-replay-comprehensive"
            ),
            "repo_slug": "platformcontext/governance-replay-comprehensive",
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
            "file_count": 2,
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
            "sample_queries": [
                {
                    "name": "governance_daily_revenue_lookup",
                    "status": "success",
                    "executed_by": "governance_audit",
                }
            ],
            "sample_dashboards": [],
            "sample_assets": [
                {"name": "analytics.finance.daily_revenue", "kind": "table"},
            ],
            "sample_quality_checks": [],
            "sample_owners": [
                {
                    "name": "Finance Analytics",
                    "team": "finance-analytics",
                }
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
        raising=False,
    )

    result = build_repository_context(_Session(), "governance-replay-comprehensive")

    assert result["data_intelligence"]["data_owner_count"] == 1
    assert result["data_intelligence"]["data_contract_count"] == 1
    assert result["data_intelligence"]["protected_column_count"] == 1
    assert result["data_intelligence"]["relationship_counts"]["owns"] == 2
    assert result["data_intelligence"]["relationship_counts"][
        "declares_contract_for"
    ] == 3
    assert result["data_intelligence"]["relationship_counts"]["masks"] == 1
    assert [
        item["name"] for item in result["data_intelligence"]["sample_contracts"]
    ] == ["daily_revenue_contract"]
