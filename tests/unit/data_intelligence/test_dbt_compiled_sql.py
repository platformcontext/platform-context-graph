"""Tests for dbt-style compiled SQL normalization."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.data_intelligence.dbt import DbtCompiledSqlPlugin

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE_PATH = (
    REPO_ROOT
    / "tests"
    / "fixtures"
    / "ecosystems"
    / "analytics_compiled_comprehensive"
    / "dbt_manifest.json"
)


def _load_fixture() -> dict[str, object]:
    """Return the checked-in dbt-style replay fixture."""

    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def test_normalize_dbt_manifest_emits_models_assets_and_dependencies() -> None:
    """Compiled manifest normalization should emit model and asset lineage."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(_load_fixture())

    assert [item["name"] for item in report["analytics_models"]] == [
        "order_metrics",
        "orders_expanded",
    ]
    assert [item["compiled_path"] for item in report["analytics_models"]] == [
        "target/compiled/jaffle_shop/models/marts/order_metrics.sql",
        "target/compiled/jaffle_shop/models/marts/orders_expanded.sql",
    ]
    assert [item["name"] for item in report["data_assets"]] == [
        "analytics.public.order_metrics",
        "analytics.public.orders_expanded",
        "raw.public.customers",
        "raw.public.orders",
        "raw.public.payments",
    ]
    assert any(
        item["type"] == "COMPILES_TO"
        and item["source_name"] == "order_metrics"
        and item["target_name"] == "analytics.public.order_metrics"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "ASSET_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics"
        and item["target_name"] == "raw.public.orders"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "ASSET_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics"
        and item["target_name"] == "raw.public.customers"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "ASSET_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics"
        and item["target_name"] == "raw.public.payments"
        for item in report["relationships"]
    )


def test_normalize_dbt_manifest_extracts_static_column_lineage() -> None:
    """Supported compiled SQL projections should emit exact column lineage."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.order_id"
        and item["target_name"] == "raw.public.orders.id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.customer_name"
        and item["target_name"] == "raw.public.customers.full_name"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.total_amount"
        and item["target_name"] == "raw.public.payments.amount"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.orders_expanded.customer_segment"
        and item["target_name"] == "raw.public.customers.segment"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.orders_expanded.id"
        and item["target_name"] == "raw.public.orders.id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.orders_expanded.customer_id"
        and item["target_name"] == "raw.public.orders.customer_id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.orders_expanded.created_at"
        and item["target_name"] == "raw.public.orders.created_at"
        for item in report["relationships"]
    )


def test_normalize_dbt_manifest_propagates_cte_lineage_to_model_columns() -> None:
    """CTE-backed final projections should resolve back to source-table columns."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(_load_fixture())

    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.order_id"
        and item["target_name"] == "raw.public.orders.id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.customer_name"
        and item["target_name"] == "raw.public.customers.full_name"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.total_amount"
        and item["target_name"] == "raw.public.payments.amount"
        for item in report["relationships"]
    )


def test_normalize_dbt_manifest_expands_known_wildcard_projections() -> None:
    """Wildcard projections should expand when the source schema is known."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(_load_fixture())

    assert report["coverage"] == {
        "confidence": 1.0,
        "state": "complete",
        "unresolved_references": [],
    }
    assert [
        item["parse_state"]
        for item in report["analytics_models"]
        if item["name"] == "orders_expanded"
    ] == ["complete"]
    assert [
        {
            "unresolved_reference_count": item["unresolved_reference_count"],
            "unresolved_reference_reasons": item["unresolved_reference_reasons"],
            "unresolved_reference_expressions": item[
                "unresolved_reference_expressions"
            ],
        }
        for item in report["analytics_models"]
        if item["name"] == "orders_expanded"
    ] == [
        {
            "unresolved_reference_count": 0,
            "unresolved_reference_reasons": [],
            "unresolved_reference_expressions": [],
        }
    ]
