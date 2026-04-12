"""Tests for quality replay normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.quality_replay import (
    QualityReplayPlugin,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "quality_replay_comprehensive"
    / "quality_replay.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in quality replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_quality_replay_emits_quality_checks() -> None:
    """Quality replay normalization should emit data-quality check nodes."""

    plugin = QualityReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["data_quality_checks"]] == [
        "daily_revenue_freshness",
        "gross_amount_non_negative",
    ]
    assert report["data_quality_checks"][0]["status"] == "passing"
    assert report["data_quality_checks"][1]["severity"] == "high"


def test_normalize_quality_replay_emits_asserts_quality_relationships() -> None:
    """Quality replay normalization should link checks to assets and columns."""

    plugin = QualityReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "ASSERTS_QUALITY_ON"
        and item["source_name"] == "daily_revenue_freshness"
        and item["target_name"] == "analytics.finance.daily_revenue"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "ASSERTS_QUALITY_ON"
        and item["source_name"] == "gross_amount_non_negative"
        and item["target_name"] == "analytics.finance.daily_revenue.gross_amount"
        for item in report["relationships"]
    )
    assert report["coverage"]["state"] == "complete"
