"""Focused classification coverage for data-intelligence change surfaces."""

from __future__ import annotations

from platform_context_graph.query.impact import find_change_surface


def test_find_change_surface_marks_protected_breaking_column_as_governance_sensitive():
    """Protected columns with breaking contracts should surface governance risk."""

    fixture = {
        "entities": [
            {
                "id": "data-column:analytics.finance.daily_revenue.customer_email",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.customer_email",
                "sensitivity": "pii",
                "is_protected": True,
                "protection_kind": "masked",
                "contract_names": ["daily_revenue_contract"],
                "contract_levels": ["gold"],
                "change_policies": ["breaking"],
            }
        ],
        "edges": [],
    }

    result = find_change_surface(
        fixture,
        target="data-column:analytics.finance.daily_revenue.customer_email",
    )

    assert result["target_change_classification"]["primary"] == "governance-sensitive"
    assert set(result["target_change_classification"]["signals"]) == {
        "breaking",
        "governance-sensitive",
    }
    assert result["classification_summary"]["highest"] == "governance-sensitive"


def test_find_change_surface_marks_additive_contract_targets_as_additive():
    """Additive contract metadata should surface as an additive source change."""

    fixture = {
        "entities": [
            {
                "id": "data-asset:analytics.finance.daily_revenue",
                "type": "data_asset",
                "name": "analytics.finance.daily_revenue",
                "contract_names": ["daily_revenue_contract"],
                "change_policies": ["additive"],
            }
        ],
        "edges": [],
    }

    result = find_change_surface(
        fixture,
        target="data-asset:analytics.finance.daily_revenue",
    )

    assert result["target_change_classification"]["primary"] == "additive"
    assert result["classification_summary"]["highest"] == "additive"


def test_find_change_surface_marks_downstream_quality_checks_as_quality_risk():
    """Downstream quality checks should classify the impact as quality-risk."""

    fixture = {
        "entities": [
            {
                "id": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.gross_amount",
            },
            {
                "id": "data-quality-check:finance:gross-amount-non-negative",
                "type": "data_quality_check",
                "name": "gross_amount_non_negative",
                "status": "failing",
                "severity": "high",
                "check_type": "assertion",
            },
        ],
        "edges": [
            {
                "from": "data-quality-check:finance:gross-amount-non-negative",
                "to": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "ASSERTS_QUALITY_ON",
                "confidence": 1.0,
                "reason": "Quality check validates the gross_amount column",
                "evidence": [
                    {
                        "source": "quality-replay",
                        "detail": "gross_amount_non_negative targets gross_amount",
                        "weight": 1.0,
                    }
                ],
            }
        ],
    }

    result = find_change_surface(
        fixture,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    impacted = next(
        item
        for item in result["impacted"]
        if item["entity"]["id"] == "data-quality-check:finance:gross-amount-non-negative"
    )
    assert impacted["change_classification"]["primary"] == "quality-risk"
    assert impacted["change_classification"]["signals"] == ["quality-risk"]
    assert result["classification_summary"]["highest"] == "quality-risk"


def test_find_change_surface_ignores_structural_only_sibling_paths_in_summary():
    """Structural-only sibling paths should not outrank real dependency risks."""

    fixture = {
        "entities": [
            {
                "id": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.gross_amount",
            },
            {
                "id": "data-column:analytics.finance.daily_revenue.customer_email",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.customer_email",
                "sensitivity": "pii",
                "is_protected": True,
                "protection_kind": "masked",
            },
            {
                "id": "data-quality-check:finance:gross-amount-non-negative",
                "type": "data_quality_check",
                "name": "gross_amount_non_negative",
                "status": "failing",
                "severity": "high",
            },
            {
                "id": "file:%2Ftmp%2Fwarehouse%2Fwarehouse_replay.json",
                "type": "file",
                "name": "warehouse_replay.json",
                "path": "/tmp/warehouse/warehouse_replay.json",
            },
        ],
        "edges": [
            {
                "from": "file:%2Ftmp%2Fwarehouse%2Fwarehouse_replay.json",
                "to": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "CONTAINS",
                "confidence": 1.0,
                "reason": "File contains gross_amount",
                "evidence": [],
            },
            {
                "from": "file:%2Ftmp%2Fwarehouse%2Fwarehouse_replay.json",
                "to": "data-column:analytics.finance.daily_revenue.customer_email",
                "type": "CONTAINS",
                "confidence": 1.0,
                "reason": "File contains customer_email",
                "evidence": [],
            },
            {
                "from": "data-quality-check:finance:gross-amount-non-negative",
                "to": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "ASSERTS_QUALITY_ON",
                "confidence": 1.0,
                "reason": "Quality check validates gross_amount",
                "evidence": [],
            },
        ],
    }

    result = find_change_surface(
        fixture,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    sibling = next(
        item
        for item in result["impacted"]
        if item["entity"]["id"] == "data-column:analytics.finance.daily_revenue.customer_email"
    )
    assert sibling["change_classification"]["primary"] == "informational"
    assert result["classification_summary"]["highest"] == "quality-risk"


def test_find_change_surface_ignores_contract_only_sibling_paths_in_summary():
    """Shared contract overlays should not turn sibling columns into risks."""

    fixture = {
        "entities": [
            {
                "id": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.gross_amount",
            },
            {
                "id": "data-column:analytics.finance.daily_revenue.customer_email",
                "type": "data_column",
                "name": "analytics.finance.daily_revenue.customer_email",
                "sensitivity": "pii",
                "is_protected": True,
                "protection_kind": "masked",
                "change_policies": ["breaking"],
            },
            {
                "id": "content-entity:e_contract_daily_revenue",
                "type": "content_entity",
                "name": "daily_revenue_contract",
            },
            {
                "id": "data-quality-check:finance:gross-amount-non-negative",
                "type": "data_quality_check",
                "name": "gross_amount_non_negative",
                "status": "failing",
                "severity": "high",
            },
        ],
        "edges": [
            {
                "from": "content-entity:e_contract_daily_revenue",
                "to": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "DECLARES_CONTRACT_FOR",
                "confidence": 1.0,
                "reason": "Contract covers gross_amount",
                "evidence": [],
            },
            {
                "from": "content-entity:e_contract_daily_revenue",
                "to": "data-column:analytics.finance.daily_revenue.customer_email",
                "type": "DECLARES_CONTRACT_FOR",
                "confidence": 1.0,
                "reason": "Contract covers customer_email",
                "evidence": [],
            },
            {
                "from": "data-quality-check:finance:gross-amount-non-negative",
                "to": "data-column:analytics.finance.daily_revenue.gross_amount",
                "type": "ASSERTS_QUALITY_ON",
                "confidence": 1.0,
                "reason": "Quality check validates gross_amount",
                "evidence": [],
            },
        ],
    }

    result = find_change_surface(
        fixture,
        target="data-column:analytics.finance.daily_revenue.gross_amount",
    )

    sibling = next(
        item
        for item in result["impacted"]
        if item["entity"]["id"] == "data-column:analytics.finance.daily_revenue.customer_email"
    )
    assert sibling["change_classification"]["primary"] == "informational"
    assert result["classification_summary"]["highest"] == "quality-risk"
