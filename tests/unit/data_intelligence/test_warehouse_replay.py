"""Tests for warehouse replay normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.warehouse_replay import (
    WarehouseReplayPlugin,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "warehouse_replay_comprehensive"
    / "warehouse_replay.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in warehouse replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_warehouse_replay_emits_assets_columns_and_queries() -> None:
    """Warehouse replay normalization should emit generic graph entities."""

    plugin = WarehouseReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["data_assets"]] == [
        "analytics.crm.customers",
        "analytics.finance.daily_revenue",
        "analytics.finance.revenue",
    ]
    assert [item["name"] for item in report["query_executions"]] == [
        "daily_revenue_build",
        "revenue_dashboard_lookup",
    ]
    assert any(
        item["name"] == "analytics.finance.revenue.amount"
        for item in report["data_columns"]
    )


def test_normalize_warehouse_replay_emits_runs_query_against_relationships() -> None:
    """Warehouse replay normalization should link query executions to assets."""

    plugin = WarehouseReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "RUNS_QUERY_AGAINST"
        and item["source_name"] == "daily_revenue_build"
        and item["target_name"] == "analytics.finance.revenue"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "RUNS_QUERY_AGAINST"
        and item["source_name"] == "revenue_dashboard_lookup"
        and item["target_name"] == "analytics.finance.daily_revenue"
        for item in report["relationships"]
    )
    assert report["coverage"]["state"] == "complete"
