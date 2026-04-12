"""Data-intelligence coverage for repository context responses."""

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
            "relationship_counts": {
                "compiles_to": 2,
                "asset_derives_from": 5,
                "column_derives_from": 4,
                "runs_query_against": 4,
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
            "sample_assets": [
                {"name": "analytics.public.order_metrics", "kind": "model"},
                {"name": "raw.public.orders", "kind": "source"},
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
    }
    assert result["data_intelligence"]["query_execution_count"] == 2
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
