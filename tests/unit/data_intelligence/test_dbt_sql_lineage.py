"""Focused tests for compiled dbt SQL lineage helpers."""

from __future__ import annotations

from platform_context_graph.data_intelligence.dbt_sql_lineage import (
    extract_compiled_model_lineage,
)

_RELATION_COLUMNS = {
    "raw.public.orders": ("id", "customer_id", "created_at"),
    "raw.public.customers": ("id", "full_name", "segment"),
    "raw.public.payments": ("order_id", "amount"),
}


def test_extract_compiled_model_lineage_resolves_unqualified_columns_from_single_cte(
) -> None:
    """Final selects should resolve bare columns when one relation is in scope."""

    lineage = extract_compiled_model_lineage(
        """
        with customer_orders as (
          select
            o.id as raw_order_id,
            c.full_name as source_customer_name
          from raw.public.orders o
          join raw.public.customers c on c.id = o.customer_id
        )
        select
          raw_order_id as order_id,
          upper(source_customer_name) as customer_name
        from customer_orders
        """,
        model_name="order_metrics",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.unresolved_references == ()
    assert [
        (item.output_column, item.source_columns) for item in lineage.column_lineage
    ] == [
        ("order_id", ("raw.public.orders.id",)),
        ("customer_name", ("raw.public.customers.full_name",)),
    ]


def test_extract_compiled_model_lineage_flags_ambiguous_unqualified_columns() -> None:
    """Bare columns should stay explicit gaps when multiple bindings can match."""

    lineage = extract_compiled_model_lineage(
        """
        select id as maybe_id
        from raw.public.orders o
        join raw.public.customers c on c.id = o.customer_id
        """,
        model_name="ambiguous_metrics",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == ()
    assert lineage.unresolved_references == (
        {
            "expression": "id",
            "model_name": "ambiguous_metrics",
            "reason": "unqualified_column_reference_ambiguous",
        },
    )
