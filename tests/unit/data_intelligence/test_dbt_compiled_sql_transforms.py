"""Transform-focused tests for dbt-style compiled SQL normalization."""

from __future__ import annotations

from platform_context_graph.data_intelligence.dbt import DbtCompiledSqlPlugin


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


def test_normalize_dbt_manifest_supports_multi_source_row_level_transforms() -> None:
    """Multi-source row-level transforms should stay on the supported path."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(
        {
            "metadata": {
                "adapter_type": "postgres",
                "project_name": "jaffle_shop",
            },
            "nodes": {
                "model.jaffle_shop.customer_enrichment": {
                    "unique_id": "model.jaffle_shop.customer_enrichment",
                    "resource_type": "model",
                    "name": "customer_enrichment",
                    "database": "analytics",
                    "schema": "public",
                    "alias": "customer_enrichment",
                    "path": "models/marts/customer_enrichment.sql",
                    "compiled_path": (
                        "target/compiled/jaffle_shop/models/marts/customer_enrichment.sql"
                    ),
                    "relation_name": "analytics.public.customer_enrichment",
                    "config": {"materialized": "view"},
                    "depends_on": {
                        "nodes": [
                            "source.jaffle_shop.raw.orders",
                            "source.jaffle_shop.raw.customers",
                            "source.jaffle_shop.raw.payments",
                        ]
                    },
                    "compiled_code": (
                        "select "
                        "concat(c.full_name, '-', c.segment) as customer_label, "
                        "case when o.customer_id = c.id then c.full_name else 'guest' end "
                        "as resolved_name, "
                        "p.amount + o.customer_id as blended_score "
                        "from raw.public.orders o "
                        "join raw.public.customers c on c.id = o.customer_id "
                        "join raw.public.payments p on p.order_id = o.id"
                    ),
                    "columns": {
                        "customer_label": {"name": "customer_label"},
                        "resolved_name": {"name": "resolved_name"},
                        "blended_score": {"name": "blended_score"},
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
        and item["source_name"] == "analytics.public.customer_enrichment.customer_label"
        and item["target_name"] == "raw.public.customers.full_name"
        and item["transform_kind"] == "concat"
        and item["transform_expression"] == "concat(c.full_name, '-', c.segment)"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.customer_label"
        and item["target_name"] == "raw.public.customers.segment"
        and item["transform_kind"] == "concat"
        and item["transform_expression"] == "concat(c.full_name, '-', c.segment)"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.resolved_name"
        and item["target_name"] == "raw.public.orders.customer_id"
        and item["transform_kind"] == "case"
        and "case when o.customer_id = c.id then c.full_name" in item["transform_expression"]
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.resolved_name"
        and item["target_name"] == "raw.public.customers.id"
        and item["transform_kind"] == "case"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.resolved_name"
        and item["target_name"] == "raw.public.customers.full_name"
        and item["transform_kind"] == "case"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.blended_score"
        and item["target_name"] == "raw.public.payments.amount"
        and item["transform_kind"] == "arithmetic"
        and item["transform_expression"] == "p.amount + o.customer_id"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.customer_enrichment.blended_score"
        and item["target_name"] == "raw.public.orders.customer_id"
        and item["transform_kind"] == "arithmetic"
        and item["transform_expression"] == "p.amount + o.customer_id"
        for item in report["relationships"]
    )
    assert report["coverage"] == {
        "confidence": 1.0,
        "state": "complete",
        "unresolved_references": [],
    }


def test_normalize_dbt_manifest_reports_template_and_macro_honesty_gaps() -> None:
    """Normalization should surface explicit templating and macro gap reasons."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(
        {
            "metadata": {
                "adapter_type": "postgres",
                "project_name": "jaffle_shop",
            },
            "nodes": {
                "model.jaffle_shop.unresolved_macros": {
                    "unique_id": "model.jaffle_shop.unresolved_macros",
                    "resource_type": "model",
                    "name": "unresolved_macros",
                    "database": "analytics",
                    "schema": "public",
                    "alias": "unresolved_macros",
                    "path": "models/marts/unresolved_macros.sql",
                    "compiled_path": (
                        "target/compiled/jaffle_shop/models/marts/unresolved_macros.sql"
                    ),
                    "relation_name": "analytics.public.unresolved_macros",
                    "config": {"materialized": "view"},
                    "depends_on": {
                        "nodes": [
                            "source.jaffle_shop.raw.orders",
                        ]
                    },
                    "compiled_code": (
                        "select "
                        "{{ dbt_utils.generate_surrogate_key(['customer_id']) }} "
                        "as templated_customer_key, "
                        "dbt_utils.generate_surrogate_key(customer_id) "
                        "as macro_customer_key "
                        "from raw.public.orders o"
                    ),
                    "columns": {
                        "templated_customer_key": {"name": "templated_customer_key"},
                        "macro_customer_key": {"name": "macro_customer_key"},
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
                        "customer_id": {"name": "customer_id"},
                    },
                }
            },
        }
    )

    assert [
        item["type"]
        for item in report["relationships"]
        if item["type"] == "COLUMN_DERIVES_FROM"
    ] == []
    assert report["coverage"] == {
        "confidence": 0.5,
        "state": "partial",
        "unresolved_references": [
            {
                "expression": "{{ dbt_utils.generate_surrogate_key(['customer_id']) }}",
                "model_name": "unresolved_macros",
                "reason": "templated_expression_not_resolved",
            },
            {
                "expression": "dbt_utils.generate_surrogate_key(customer_id)",
                "model_name": "unresolved_macros",
                "reason": "macro_expression_not_resolved",
            },
        ],
    }
    assert report["analytics_models"] == [
        {
            "id": "analytics-model:model.jaffle_shop.unresolved_macros",
            "name": "unresolved_macros",
            "asset_name": "analytics.public.unresolved_macros",
            "line_number": 1,
            "path": "target/compiled/jaffle_shop/models/marts/unresolved_macros.sql",
            "compiled_path": "target/compiled/jaffle_shop/models/marts/unresolved_macros.sql",
            "materialization": "view",
            "parse_state": "partial",
            "confidence": 0.5,
            "projection_count": 2,
            "unresolved_reference_count": 2,
            "unresolved_reference_reasons": [
                "templated_expression_not_resolved",
                "macro_expression_not_resolved",
            ],
            "unresolved_reference_expressions": [
                "{{ dbt_utils.generate_surrogate_key(['customer_id']) }}",
                "dbt_utils.generate_surrogate_key(customer_id)",
            ],
        }
    ]


def test_normalize_dbt_manifest_preserves_window_transform_metadata() -> None:
    """Window transforms should keep metadata while remaining honestly partial."""

    plugin = DbtCompiledSqlPlugin()

    report = plugin.normalize(
        {
            "metadata": {
                "adapter_type": "postgres",
                "project_name": "jaffle_shop",
            },
            "nodes": {
                "model.jaffle_shop.window_metrics": {
                    "unique_id": "model.jaffle_shop.window_metrics",
                    "resource_type": "model",
                    "name": "window_metrics",
                    "database": "analytics",
                    "schema": "public",
                    "alias": "window_metrics",
                    "path": "models/marts/window_metrics.sql",
                    "compiled_path": (
                        "target/compiled/jaffle_shop/models/marts/window_metrics.sql"
                    ),
                    "relation_name": "analytics.public.window_metrics",
                    "config": {"materialized": "view"},
                    "depends_on": {
                        "nodes": [
                            "source.jaffle_shop.raw.payments",
                        ]
                    },
                    "compiled_code": (
                        "select "
                        "sum(p.amount) over (partition by p.order_id) "
                        "as running_amount "
                        "from raw.public.payments p"
                    ),
                    "columns": {
                        "running_amount": {"name": "running_amount"},
                    },
                }
            },
            "sources": {
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
                }
            },
        }
    )

    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.window_metrics.running_amount"
        and item["target_name"] == "raw.public.payments.amount"
        and item["transform_kind"] == "window_sum"
        and item["transform_expression"] == "sum(p.amount) over (partition by p.order_id)"
        for item in report["relationships"]
    )
    assert any(
        item["type"] == "COLUMN_DERIVES_FROM"
        and item["source_name"] == "analytics.public.window_metrics.running_amount"
        and item["target_name"] == "raw.public.payments.order_id"
        and item["transform_kind"] == "window_sum"
        and item["transform_expression"] == "sum(p.amount) over (partition by p.order_id)"
        for item in report["relationships"]
    )
    assert report["coverage"] == {
        "confidence": 0.5,
        "state": "partial",
        "unresolved_references": [
            {
                "expression": "sum(p.amount) over (partition by p.order_id)",
                "model_name": "window_metrics",
                "reason": "window_expression_semantics_not_captured",
            },
        ],
    }
    assert report["analytics_models"] == [
        {
            "id": "analytics-model:model.jaffle_shop.window_metrics",
            "name": "window_metrics",
            "asset_name": "analytics.public.window_metrics",
            "line_number": 1,
            "path": "target/compiled/jaffle_shop/models/marts/window_metrics.sql",
            "compiled_path": "target/compiled/jaffle_shop/models/marts/window_metrics.sql",
            "materialization": "view",
            "parse_state": "partial",
            "confidence": 0.5,
            "projection_count": 1,
            "unresolved_reference_count": 1,
            "unresolved_reference_reasons": [
                "window_expression_semantics_not_captured",
            ],
            "unresolved_reference_expressions": [
                "sum(p.amount) over (partition by p.order_id)",
            ],
        }
    ]
