"""Graph-backed integration tests for data change classification."""

from __future__ import annotations

import os

import pytest

from platform_context_graph.query.impact import find_change_surface

pytestmark = pytest.mark.skipif(
    not os.getenv("NEO4J_URI"),
    reason="NEO4J_URI not set — start Neo4j with docker compose up -d",
)


def test_quality_replay_change_surface_marks_downstream_checks_as_quality_risk(
    indexed_ecosystems,
) -> None:
    """Real replay fixtures should classify downstream checks as quality-risk."""

    result = find_change_surface(
        indexed_ecosystems,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    impacted = next(
        item
        for item in result["impacted"]
        if item["entity"]["id"] == "data-quality-check:finance:gross-amount-non-negative"
    )
    assert impacted["change_classification"]["primary"] == "quality-risk"
    assert result["classification_summary"]["highest"] == "quality-risk"


def test_governance_replay_change_surface_marks_protected_columns_as_governance_sensitive(
    indexed_ecosystems,
) -> None:
    """Protected contract-bound columns should classify the source as governance-sensitive."""

    result = find_change_surface(
        indexed_ecosystems,
        target="data-column:analytics.finance.daily_revenue.customer_email",
    )

    assert result["target_change_classification"]["primary"] == "governance-sensitive"
    assert set(result["target_change_classification"]["signals"]) == {
        "breaking",
        "governance-sensitive",
    }
    assert result["classification_summary"]["highest"] == "governance-sensitive"

