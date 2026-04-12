"""Tests for semantic replay normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.semantic_replay import (
    SemanticReplayPlugin,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "semantic_replay_comprehensive"
    / "semantic_replay.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in semantic replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_semantic_replay_emits_semantic_assets_and_fields() -> None:
    """Semantic replay normalization should emit generic asset and column nodes."""

    plugin = SemanticReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["data_assets"]] == [
        "semantic.finance.revenue_semantic"
    ]
    assert [item["name"] for item in report["data_columns"]] == [
        "semantic.finance.revenue_semantic.customer_tier",
        "semantic.finance.revenue_semantic.gross_amount",
    ]


def test_normalize_semantic_replay_emits_asset_and_column_lineage() -> None:
    """Semantic replay normalization should emit semantic lineage edges."""

    plugin = SemanticReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "ASSET_DERIVES_FROM"
        and item["source_name"] == "semantic.finance.revenue_semantic"
        and item["target_name"] == "analytics.finance.daily_revenue"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "semantic.finance.revenue_semantic.gross_amount"
        and item["target_name"] == "analytics.finance.daily_revenue.gross_amount"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "semantic.finance.revenue_semantic.customer_tier"
        and item["target_name"] == "analytics.crm.customers.customer_tier"
        for item in report["relationships"]
    )
    assert report["coverage"]["state"] == "complete"
