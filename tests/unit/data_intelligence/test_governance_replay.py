"""Tests for governance replay normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.governance_replay import (
    GovernanceReplayPlugin,
)

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "governance_replay_comprehensive"
    / "governance_replay.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in governance replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_governance_replay_emits_owner_and_contract_nodes() -> None:
    """Governance replay normalization should emit owner and contract records."""

    plugin = GovernanceReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["data_owners"]] == ["Finance Analytics"]
    assert report["data_owners"][0]["team"] == "finance-analytics"
    assert [item["name"] for item in report["data_contracts"]] == [
        "daily_revenue_contract"
    ]
    assert report["data_contracts"][0]["contract_level"] == "gold"
    assert report["data_contracts"][0]["change_policy"] == "breaking"


def test_normalize_governance_replay_emits_relationships_and_annotations() -> None:
    """Governance replay normalization should emit edges and target overlays."""

    plugin = GovernanceReplayPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "OWNS"
        and item["source_name"] == "Finance Analytics"
        and item["target_name"] == "analytics.finance.daily_revenue"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "DECLARES_CONTRACT_FOR"
        and item["source_name"] == "daily_revenue_contract"
        and item["target_name"] == "analytics.finance.daily_revenue.customer_email"
        for item in report["relationships"]
    )
    assert any(
        item["target_name"] == "analytics.finance.daily_revenue.customer_email"
        and item["is_protected"] is True
        and item["sensitivity"] == "pii"
        and item["owner_names"] == ["Finance Analytics"]
        and item["contract_names"] == ["daily_revenue_contract"]
        for item in report["governance_annotations"]
    )
    assert report["coverage"]["state"] == "complete"

