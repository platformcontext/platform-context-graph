"""Focused tests for governance replay JSON parsing."""

from __future__ import annotations

from pathlib import Path

from platform_context_graph.parsers.languages.json_config import (
    JSONConfigTreeSitterParser,
)


def test_parse_governance_replay_json_into_data_intelligence_payload(
    temp_test_dir: Path,
) -> None:
    """Governance replay JSON should emit owners, contracts, and annotations."""

    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "ecosystems"
        / "governance_replay_comprehensive"
        / "governance_replay.json"
    )
    file_path = temp_test_dir / "governance_replay.json"
    file_path.write_text(fixture_path.read_text(encoding="utf-8"), encoding="utf-8")

    parser = JSONConfigTreeSitterParser("json")
    result = parser.parse(file_path)

    assert [item["name"] for item in result["data_owners"]] == ["Finance Analytics"]
    assert [item["name"] for item in result["data_contracts"]] == [
        "daily_revenue_contract"
    ]
    assert any(
        item["type"] == "OWNS"
        and item["source_name"] == "Finance Analytics"
        and item["target_name"] == "analytics.finance.daily_revenue"
        for item in result["data_relationships"]
    )
    assert any(
        item["target_name"] == "analytics.finance.daily_revenue.customer_email"
        and item["is_protected"] is True
        for item in result["data_governance_annotations"]
    )
    assert result["data_intelligence_coverage"]["state"] == "complete"
