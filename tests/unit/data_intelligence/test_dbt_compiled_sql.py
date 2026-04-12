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
        and item["transform_kind"] == "upper"
        and item["transform_expression"] == "upper(source_customer_name)"
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
        and item["transform_kind"] == "coalesce"
        and item["transform_expression"] == "coalesce(c.segment, 'unknown')"
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


def test_normalize_dbt_manifest_supports_simple_scalar_wrappers() -> None:
    """Simple scalar wrappers should stop inflating partial coverage noise."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(_load_fixture())

    assert report["coverage"] == {
        "confidence": 0.75,
        "state": "partial",
        "unresolved_references": [
            {
                "expression": "sum(p.amount)",
                "model_name": "order_metrics",
                "reason": "aggregate_expression_semantics_not_captured",
            },
        ],
    }
    assert [
        {
            "name": item["name"],
            "parse_state": item["parse_state"],
            "confidence": item["confidence"],
            "unresolved_reference_count": item["unresolved_reference_count"],
            "unresolved_reference_reasons": item["unresolved_reference_reasons"],
            "unresolved_reference_expressions": item[
                "unresolved_reference_expressions"
            ],
        }
        for item in report["analytics_models"]
    ] == [
        {
            "name": "order_metrics",
            "parse_state": "partial",
            "confidence": 0.5,
            "unresolved_reference_count": 1,
            "unresolved_reference_reasons": [
                "aggregate_expression_semantics_not_captured"
            ],
            "unresolved_reference_expressions": [
                "sum(p.amount)",
            ],
        },
        {
            "name": "orders_expanded",
            "parse_state": "complete",
            "confidence": 1.0,
            "unresolved_reference_count": 0,
            "unresolved_reference_reasons": [],
            "unresolved_reference_expressions": [],
        },
    ]


def test_normalize_dbt_manifest_supports_typed_scalar_transforms() -> None:
    """Typed row-preserving transforms should remain complete lineage."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(
        {
            "metadata": {
                "adapter_type": "postgres",
                "project_name": "jaffle_shop",
            },
            "nodes": {
                "model.jaffle_shop.typed_orders": {
                    "unique_id": "model.jaffle_shop.typed_orders",
                    "resource_type": "model",
                    "name": "typed_orders",
                    "database": "analytics",
                    "schema": "public",
                    "alias": "typed_orders",
                    "path": "models/marts/typed_orders.sql",
                    "compiled_path": (
                        "target/compiled/jaffle_shop/models/marts/typed_orders.sql"
                    ),
                    "relation_name": "analytics.public.typed_orders",
                    "config": {"materialized": "view"},
                    "depends_on": {
                        "nodes": [
                            "source.jaffle_shop.raw.orders",
                        ]
                    },
                    "compiled_code": (
                        "select "
                        "cast(o.id as bigint) as order_id_bigint, "
                        "date_trunc('day', o.created_at) as created_day "
                        "from raw.public.orders o"
                    ),
                    "columns": {
                        "order_id_bigint": {"name": "order_id_bigint"},
                        "created_day": {"name": "created_day"},
                    },
                }
            },
            "sources": {
                "source.jaffle_shop.raw.orders": {
                    "unique_id": "source.jaffle_shop.raw.orders",
                    "resource_type": "source",
                    "source_name": "raw",
                    "name": "orders",
                    "database": "raw",
                    "schema": "public",
                    "identifier": "orders",
                    "columns": {
                        "id": {"name": "id"},
                        "created_at": {"name": "created_at"},
                    },
                }
            },
        }
    )

    assert report["coverage"] == {
        "confidence": 1.0,
        "state": "complete",
        "unresolved_references": [],
    }
    assert report["analytics_models"] == [
        {
            "id": "analytics-model:model.jaffle_shop.typed_orders",
            "name": "typed_orders",
            "asset_name": "analytics.public.typed_orders",
            "line_number": 1,
            "path": "target/compiled/jaffle_shop/models/marts/typed_orders.sql",
            "compiled_path": "target/compiled/jaffle_shop/models/marts/typed_orders.sql",
            "materialization": "view",
            "parse_state": "complete",
            "confidence": 1.0,
            "projection_count": 2,
            "unresolved_reference_count": 0,
            "unresolved_reference_reasons": [],
            "unresolved_reference_expressions": [],
        }
    ]
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.typed_orders.order_id_bigint"
        and item["target_name"] == "raw.public.orders.id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.typed_orders.created_day"
        and item["target_name"] == "raw.public.orders.created_at"
        for item in report["relationships"]
    )


def test_normalize_dbt_manifest_supports_case_and_arithmetic_transforms() -> None:
    """Common one-column derived transforms should stay on the supported path."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(
        {
            "metadata": {
                "adapter_type": "postgres",
                "project_name": "jaffle_shop",
            },
            "nodes": {
                "model.jaffle_shop.derived_metrics": {
                    "unique_id": "model.jaffle_shop.derived_metrics",
                    "resource_type": "model",
                    "name": "derived_metrics",
                    "database": "analytics",
                    "schema": "public",
                    "alias": "derived_metrics",
                    "path": "models/marts/derived_metrics.sql",
                    "compiled_path": (
                        "target/compiled/jaffle_shop/models/marts/derived_metrics.sql"
                    ),
                    "relation_name": "analytics.public.derived_metrics",
                    "config": {"materialized": "view"},
                    "depends_on": {
                        "nodes": [
                            "source.jaffle_shop.raw.customers",
                            "source.jaffle_shop.raw.payments",
                        ]
                    },
                    "compiled_code": (
                        "select "
                        "case when c.segment is null then 'unknown' else c.segment end "
                        "as normalized_segment, "
                        "p.amount * 100 as amount_cents "
                        "from raw.public.customers c "
                        "join raw.public.payments p on p.order_id = 1"
                    ),
                    "columns": {
                        "normalized_segment": {"name": "normalized_segment"},
                        "amount_cents": {"name": "amount_cents"},
                    },
                }
            },
            "sources": {
                "source.jaffle_shop.raw.customers": {
                    "unique_id": "source.jaffle_shop.raw.customers",
                    "resource_type": "source",
                    "source_name": "raw",
                    "name": "customers",
                    "database": "raw",
                    "schema": "public",
                    "identifier": "customers",
                    "columns": {
                        "id": {"name": "id"},
                        "segment": {"name": "segment"},
                    },
                },
                "source.jaffle_shop.raw.payments": {
                    "unique_id": "source.jaffle_shop.raw.payments",
                    "resource_type": "source",
                    "source_name": "raw",
                    "name": "payments",
                    "database": "raw",
                    "schema": "public",
                    "identifier": "payments",
                    "columns": {
                        "order_id": {"name": "order_id"},
                        "amount": {"name": "amount"},
                    },
                },
            },
        }
    )

    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.derived_metrics.normalized_segment"
        and item["target_name"] == "raw.public.customers.segment"
        and item["transform_kind"] == "case"
        and "case when c.segment is null" in item["transform_expression"]
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.derived_metrics.amount_cents"
        and item["target_name"] == "raw.public.payments.amount"
        and item["transform_kind"] == "arithmetic"
        and item["transform_expression"] == "p.amount * 100"
        for item in report["relationships"]
    )
    assert report["coverage"] == {
        "confidence": 1.0,
        "state": "complete",
        "unresolved_references": [],
    }
