"""Tests for BI replay normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.bi_replay import BIReplayPlugin

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "bi_replay_comprehensive"
    / "bi_replay.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in BI replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_bi_replay_emits_dashboard_assets() -> None:
    """BI replay normalization should emit dashboard assets."""

    plugin = BIReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["dashboard_assets"]] == [
        "Revenue Overview"
    ]


def test_normalize_bi_replay_emits_powers_relationships() -> None:
    """BI replay normalization should link assets and columns to dashboards."""

    plugin = BIReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "POWERS"
        and item["source_name"] == "analytics.finance.daily_revenue"
        and item["target_name"] == "Revenue Overview"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "POWERS"
        and item["source_name"] == "analytics.finance.daily_revenue.gross_amount"
        and item["target_name"] == "Revenue Overview"
        for item in report["relationships"]
    )
    assert report["coverage"]["state"] == "complete"
