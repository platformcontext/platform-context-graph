"""Observed-usage summaries for repository data-intelligence context."""

from __future__ import annotations

from platform_context_graph.query.repositories.context_data_intelligence import (
    _observed_usage_summary,
)


class _Result:
    """Minimal query result wrapper for repository usage-summary tests."""

    def __init__(self, rows: list[dict[str, object]]) -> None:
        self._rows = rows

    def data(self) -> list[dict[str, object]]:
        return self._rows


class _ObservedUsageSession:
    """Minimal session stub returning deterministic observed usage counts."""

    def run(self, query: str, **_kwargs: object) -> _Result:
        assert "MATCH (q)-[:RUNS_QUERY_AGAINST]->(asset:DataAsset)" in query
        assert "count(DISTINCT q) AS query_count" in query
        return _Result(
            [
                {"name": "analytics.finance.daily_revenue", "query_count": 2},
                {"name": "analytics.crm.customers", "query_count": 1},
                {"name": "analytics.finance.revenue", "query_count": 1},
            ]
        )


def test_observed_usage_summary_classifies_hot_and_low_use_assets() -> None:
    """Observed replay counts should classify hot and low-use assets."""

    result = _observed_usage_summary(
        _ObservedUsageSession(),
        {"id": "repository:r_demo", "name": "warehouse_replay_comprehensive"},
    )

    assert result == {
        "hot_asset_count": 1,
        "low_use_asset_count": 2,
        "max_query_count": 2,
        "hot_assets": [
            {"name": "analytics.finance.daily_revenue", "query_count": 2},
        ],
        "low_use_assets": [
            {"name": "analytics.crm.customers", "query_count": 1},
            {"name": "analytics.finance.revenue", "query_count": 1},
        ],
    }
