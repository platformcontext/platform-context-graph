package parser

import (
	"reflect"
	"testing"
)

func TestExtractCompiledModelLineageCapturesMacroProjectionWithoutUnresolvedGap(t *testing.T) {
	t.Parallel()

	got := extractCompiledModelLineage(
		`select
  dbt_utils.identity(o.amount) as macro_amount
from raw.public.orders o`,
		"order_metrics",
		map[string][]string{
			"raw.public.orders": {"amount"},
		},
	)

	if got.ProjectionCount != 1 {
		t.Fatalf("ProjectionCount = %d, want 1", got.ProjectionCount)
	}
	if len(got.UnresolvedReferences) != 0 {
		t.Fatalf("UnresolvedReferences = %#v, want none", got.UnresolvedReferences)
	}

	want := []ColumnLineage{
		{
			OutputColumn:  "macro_amount",
			SourceColumns: []string{"raw.public.orders.amount"},
		},
	}
	if !reflect.DeepEqual(got.ColumnLineage, want) {
		t.Fatalf("ColumnLineage = %#v, want %#v", got.ColumnLineage, want)
	}
}

func TestExtractCompiledModelLineageCapturesWindowProjectionWithoutUnresolvedGap(t *testing.T) {
	t.Parallel()

	got := extractCompiledModelLineage(
		`select
  sum(o.amount) over (partition by o.customer_id order by o.order_date) as rolling_amount
from raw.public.orders o`,
		"order_metrics",
		map[string][]string{
			"raw.public.orders": {"amount", "customer_id", "order_date"},
		},
	)

	if got.ProjectionCount != 1 {
		t.Fatalf("ProjectionCount = %d, want 1", got.ProjectionCount)
	}
	if len(got.UnresolvedReferences) != 0 {
		t.Fatalf("UnresolvedReferences = %#v, want none", got.UnresolvedReferences)
	}

	want := []ColumnLineage{
		{
			OutputColumn: "rolling_amount",
			SourceColumns: []string{
				"raw.public.orders.amount",
				"raw.public.orders.customer_id",
				"raw.public.orders.order_date",
			},
			TransformKind:       "window_sum",
			TransformExpression: "sum(o.amount) over (partition by o.customer_id order by o.order_date)",
		},
	}
	if !reflect.DeepEqual(got.ColumnLineage, want) {
		t.Fatalf("ColumnLineage = %#v, want %#v", got.ColumnLineage, want)
	}
}
