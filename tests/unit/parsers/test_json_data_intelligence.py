"""Focused JSON parser tests for data-intelligence manifest fixtures."""

from __future__ import annotations

import json
from pathlib import Path

from platform_context_graph.parsers.languages.json_config import (
    JSONConfigTreeSitterParser,
)


def test_parse_dbt_manifest_into_data_intelligence_payload(
    temp_test_dir: Path,
) -> None:
    """dbt manifest JSON should emit analytics entities and lineage hints."""

    file_path = temp_test_dir / "manifest.json"
    file_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "adapter_type": "postgres",
                    "project_name": "jaffle_shop",
                },
                "nodes": {
                    "model.jaffle_shop.order_metrics": {
                        "unique_id": "model.jaffle_shop.order_metrics",
                        "resource_type": "model",
                        "name": "order_metrics",
                        "database": "analytics",
                        "schema": "public",
                        "alias": "order_metrics",
                        "path": "models/marts/order_metrics.sql",
                        "compiled_path": (
                            "target/compiled/jaffle_shop/"
                            "models/marts/order_metrics.sql"
                        ),
                        "relation_name": "analytics.public.order_metrics",
                        "config": {"materialized": "view"},
                        "depends_on": {
                            "nodes": [
                                "source.jaffle_shop.raw.orders",
                                "source.jaffle_shop.raw.customers",
                            ]
                        },
                        "compiled_code": (
                            "select o.id as order_id, "
                            "c.full_name as customer_name "
                            "from raw.public.orders o "
                            "join raw.public.customers c on c.id = o.customer_id"
                        ),
                        "columns": {
                            "order_id": {"name": "order_id"},
                            "customer_name": {"name": "customer_name"},
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
                            "customer_id": {"name": "customer_id"},
                        },
                    },
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
                            "full_name": {"name": "full_name"},
                        },
                    },
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    parser = JSONConfigTreeSitterParser("json")
    result = parser.parse(file_path)

    assert [item["name"] for item in result["analytics_models"]] == ["order_metrics"]
    assert [item["name"] for item in result["data_assets"]] == [
        "analytics.public.order_metrics",
        "raw.public.customers",
        "raw.public.orders",
    ]
    assert any(
        item["type"] == "COMPILES_TO"
        and item["source_name"] == "order_metrics"
        and item["target_name"] == "analytics.public.order_metrics"
        for item in result["data_relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.order_metrics.customer_name"
        and item["target_name"] == "raw.public.customers.full_name"
        for item in result["data_relationships"]
    )
    assert result["data_intelligence_coverage"]["state"] == "complete"


def test_parse_dbt_replay_manifest_filename_variant(
    temp_test_dir: Path,
) -> None:
    """Replay fixtures named ``dbt_manifest.json`` should parse as dbt artifacts."""

    manifest_path = temp_test_dir / "dbt_manifest.json"
    source_path = (
        Path(__file__).resolve().parents[2]
        / "fixtures"
        / "ecosystems"
        / "analytics_compiled_comprehensive"
        / "dbt_manifest.json"
    )
    manifest_path.write_text(source_path.read_text(encoding="utf-8"), encoding="utf-8")

    parser = JSONConfigTreeSitterParser("json")
    result = parser.parse(manifest_path)

    assert [item["name"] for item in result["analytics_models"]] == [
        "order_metrics",
        "orders_expanded",
    ]
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.orders_expanded.id"
        and item["target_name"] == "raw.public.orders.id"
        for item in result["data_relationships"]
    )
    assert result["data_intelligence_coverage"]["state"] == "partial"
    assert result["data_intelligence_coverage"]["unresolved_references"] == [
        {
            "expression": "sum(p.amount)",
            "model_name": "order_metrics",
            "reason": "derived_expression_semantics_not_captured",
        },
    ]
