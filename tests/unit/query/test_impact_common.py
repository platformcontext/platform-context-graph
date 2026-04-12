"""Focused tests for impact-query record normalization helpers."""

from __future__ import annotations

from platform_context_graph.query.impact.common import entity_from_record


def test_entity_from_record_preserves_analytics_lineage_coverage_fields() -> None:
    """Analytics-model records should keep partial-lineage coverage metadata."""

    result = entity_from_record(
        {
            "id": "analytics-model:model.jaffle_shop.orders_expanded",
            "type": "analytics_model",
            "name": "orders_expanded",
            "path": "target/compiled/jaffle_shop/models/marts/orders_expanded.sql",
            "repo_id": "repository:r_analytics",
            "parse_state": "partial",
            "confidence": 0.5,
            "materialization": "view",
            "projection_count": 2,
            "unresolved_reference_count": 1,
            "unresolved_reference_reasons": ["wildcard_projection_not_supported"],
            "unresolved_reference_expressions": ["o.*"],
        }
    )

    assert result == {
        "id": "analytics-model:model.jaffle_shop.orders_expanded",
        "type": "analytics_model",
        "name": "orders_expanded",
        "repo_id": "repository:r_analytics",
        "path": "target/compiled/jaffle_shop/models/marts/orders_expanded.sql",
        "parse_state": "partial",
        "confidence": 0.5,
        "materialization": "view",
        "projection_count": 2,
        "unresolved_reference_count": 1,
        "unresolved_reference_reasons": ["wildcard_projection_not_supported"],
        "unresolved_reference_expressions": ["o.*"],
    }
