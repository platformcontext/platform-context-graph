"""Focused tests for compiled dbt SQL lineage helpers."""

from __future__ import annotations

from platform_context_graph.data_intelligence.dbt_sql_lineage import (
    ColumnLineage,
    extract_compiled_model_lineage,
)

_RELATION_COLUMNS = {
    "raw.public.orders": ("id", "customer_id", "created_at"),
    "raw.public.customers": ("id", "full_name", "segment"),
    "raw.public.payments": ("order_id", "amount"),
}


def test_extract_compiled_model_lineage_supports_single_column_upper_wrapper(
) -> None:
    """Simple one-column scalar wrappers should count as supported lineage."""

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
        (
            item.output_column,
            item.source_columns,
            item.transform_kind,
            item.transform_expression,
        )
        for item in lineage.column_lineage
    ] == [
        ("order_id", ("raw.public.orders.id",), None, None),
        (
            "customer_name",
            ("raw.public.customers.full_name",),
            "upper",
            "upper(source_customer_name)",
        ),
    ]


def test_extract_compiled_model_lineage_supports_coalesce_with_literal_default(
) -> None:
    """Coalesce should stay supported when one source column feeds a literal fallback."""

    lineage = extract_compiled_model_lineage(
        """
        select
          coalesce(c.segment, 'unknown') as customer_segment
        from raw.public.customers c
        """,
        model_name="customer_segments",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="customer_segment",
            source_columns=("raw.public.customers.segment",),
            transform_kind="coalesce",
            transform_expression="coalesce(c.segment, 'unknown')",
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_supports_cast_wrapper() -> None:
    """CAST of one source column should stay on the supported lineage path."""

    lineage = extract_compiled_model_lineage(
        """
        select
          cast(o.id as bigint) as order_id_bigint
        from raw.public.orders o
        """,
        model_name="typed_orders",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="order_id_bigint",
            source_columns=("raw.public.orders.id",),
            transform_kind="cast",
            transform_expression="cast(o.id as bigint)",
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_supports_literal_parameter_wrappers() -> None:
    """Literal-parameter wrappers should stay supported with one source column."""

    lineage = extract_compiled_model_lineage(
        """
        select
          date_trunc('day', o.created_at) as created_day
        from raw.public.orders o
        """,
        model_name="typed_orders",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="created_day",
            source_columns=("raw.public.orders.created_at",),
            transform_kind="date_trunc",
            transform_expression="date_trunc('day', o.created_at)",
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_supports_single_source_case_expression(
) -> None:
    """One-column CASE transforms should stay on the supported lineage path."""

    lineage = extract_compiled_model_lineage(
        """
        select
          case
            when c.segment is null then 'unknown'
            else c.segment
          end as normalized_segment
        from raw.public.customers c
        """,
        model_name="customer_segments",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="normalized_segment",
            source_columns=("raw.public.customers.segment",),
            transform_kind="case",
            transform_expression=(
                "case\n"
                "            when c.segment is null then 'unknown'\n"
                "            else c.segment\n"
                "          end"
            ),
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_supports_single_source_arithmetic(
) -> None:
    """One-column arithmetic with literal operands should stay supported."""

    lineage = extract_compiled_model_lineage(
        """
        select
          p.amount * 100 as amount_cents
        from raw.public.payments p
        """,
        model_name="payment_metrics",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="amount_cents",
            source_columns=("raw.public.payments.amount",),
            transform_kind="arithmetic",
            transform_expression="p.amount * 100",
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_propagates_cte_transform_metadata() -> None:
    """Direct selects from transformed CTE columns should preserve metadata."""

    lineage = extract_compiled_model_lineage(
        """
        with normalized_customers as (
          select
            upper(c.full_name) as normalized_name
          from raw.public.customers c
        )
        select
          normalized_name as customer_name
        from normalized_customers
        """,
        model_name="customer_names",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="customer_name",
            source_columns=("raw.public.customers.full_name",),
            transform_kind="upper",
            transform_expression="upper(c.full_name)",
        ),
    )
    assert lineage.unresolved_references == ()


def test_extract_compiled_model_lineage_marks_aggregate_projection_partial() -> None:
    """Aggregate projections should retain source lineage and surface a gap."""

    lineage = extract_compiled_model_lineage(
        """
        select
          sum(p.amount) as total_amount
        from raw.public.payments p
        """,
        model_name="payment_metrics",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="total_amount",
            source_columns=("raw.public.payments.amount",),
        ),
    )
    assert lineage.unresolved_references == (
        {
            "expression": "sum(p.amount)",
            "model_name": "payment_metrics",
            "reason": "aggregate_expression_semantics_not_captured",
        },
    )


def test_extract_compiled_model_lineage_keeps_multi_input_expressions_partial() -> None:
    """Multi-input transforms should remain partial until semantics are modeled."""

    lineage = extract_compiled_model_lineage(
        """
        select
          concat(c.full_name, '-', c.segment) as customer_label
        from raw.public.customers c
        """,
        model_name="customer_labels",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="customer_label",
            source_columns=(
                "raw.public.customers.full_name",
                "raw.public.customers.segment",
            ),
        ),
    )
    assert lineage.unresolved_references == (
        {
            "expression": "concat(c.full_name, '-', c.segment)",
            "model_name": "customer_labels",
            "reason": "multi_input_expression_semantics_not_captured",
        },
    )


def test_extract_compiled_model_lineage_keeps_multi_source_case_partial() -> None:
    """CASE expressions with multiple source columns should remain partial."""

    lineage = extract_compiled_model_lineage(
        """
        select
          case
            when o.customer_id = c.id then c.full_name
            else 'guest'
          end as resolved_name
        from raw.public.orders o
        join raw.public.customers c on c.id = o.customer_id
        """,
        model_name="customer_labels",
        relation_column_names=_RELATION_COLUMNS,
    )

    assert lineage.column_lineage == (
        ColumnLineage(
            output_column="resolved_name",
            source_columns=(
                "raw.public.orders.customer_id",
                "raw.public.customers.id",
                "raw.public.customers.full_name",
            ),
        ),
    )
    assert lineage.unresolved_references == (
        {
            "expression": (
                "case\n"
                "            when o.customer_id = c.id then c.full_name\n"
                "            else 'guest'\n"
                "          end"
            ),
            "model_name": "customer_labels",
            "reason": "derived_expression_semantics_not_captured",
        },
    )


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
