package parser

import (
	"reflect"
	"testing"
)

func TestApplyDBTManifestDocumentIncludesMacroDependenciesAndLineage(t *testing.T) {
	t.Parallel()

	payload := map[string]any{}
	document := map[string]any{
		"metadata": map[string]any{
			"adapter_type": "postgres",
			"project_name": "jaffle_shop",
		},
		"nodes": map[string]any{
			"model.jaffle_shop.order_metrics": map[string]any{
				"unique_id":     "model.jaffle_shop.order_metrics",
				"resource_type": "model",
				"name":          "order_metrics",
				"database":      "analytics",
				"schema":        "public",
				"alias":         "order_metrics",
				"path":          "models/marts/order_metrics.sql",
				"compiled_path": "target/compiled/jaffle_shop/models/marts/order_metrics.sql",
				"relation_name": "analytics.public.order_metrics",
				"config":        map[string]any{"materialized": "view"},
				"depends_on":    map[string]any{"nodes": []any{"source.jaffle_shop.raw.orders"}, "macros": []any{"macro.jaffle_shop.generate_surrogate_key"}},
				"compiled_code": "select dbt_utils.generate_surrogate_key(md5(o.id)) as surrogate_key from raw.public.orders o",
				"columns":       map[string]any{"surrogate_key": map[string]any{"name": "surrogate_key"}},
			},
		},
		"sources": map[string]any{
			"source.jaffle_shop.raw.orders": map[string]any{
				"unique_id":     "source.jaffle_shop.raw.orders",
				"resource_type": "source",
				"source_name":   "raw",
				"name":          "orders",
				"database":      "raw",
				"schema":        "public",
				"identifier":    "orders",
				"columns":       map[string]any{"id": map[string]any{"name": "id"}},
			},
		},
		"macros": map[string]any{
			"macro.jaffle_shop.generate_surrogate_key": map[string]any{
				"unique_id":     "macro.jaffle_shop.generate_surrogate_key",
				"resource_type": "macro",
				"package_name":  "dbt_utils",
				"name":          "generate_surrogate_key",
				"macro_sql":     "{{ return(arg) }}",
			},
		},
	}

	applyDBTManifestDocument(payload, document)

	if got, want := dbtBucketNames(t, payload, "analytics_models"), []string{"order_metrics"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("analytics models = %#v, want %#v", got, want)
	}
	if got, want := dbtBucketNames(t, payload, "data_assets"), []string{
		"dbt_utils.generate_surrogate_key",
		"analytics.public.order_metrics",
		"raw.public.orders",
	}; !reflect.DeepEqual(got, want) {
		t.Fatalf("data assets = %#v, want %#v", got, want)
	}
	dbtAssertRelationshipPresent(t, payload, "COMPILES_TO", "order_metrics", "analytics.public.order_metrics")
	dbtAssertRelationshipPresent(t, payload, "USES_MACRO", "analytics.public.order_metrics", "dbt_utils.generate_surrogate_key")
	dbtAssertRelationshipPresent(t, payload, "COLUMN_DERIVES_FROM", "analytics.public.order_metrics.surrogate_key", "raw.public.orders.id")
	dbtAssertCoverageState(t, payload, "complete")
}

func dbtBucketNames(t *testing.T, payload map[string]any, key string) []string {
	t.Helper()

	items, ok := payload[key].([]map[string]any)
	if ok {
		names := make([]string, 0, len(items))
		for _, item := range items {
			name, _ := item["name"].(string)
			names = append(names, name)
		}
		return names
	}

	rawItems, ok := payload[key].([]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any or []any", key, payload[key])
	}
	names := make([]string, 0, len(rawItems))
	for _, rawItem := range rawItems {
		item := rawItem.(map[string]any)
		name, _ := item["name"].(string)
		names = append(names, name)
	}
	return names
}

func dbtAssertRelationshipPresent(t *testing.T, payload map[string]any, relationshipType string, sourceName string, targetName string) {
	t.Helper()

	items, ok := payload["data_relationships"].([]map[string]any)
	if !ok {
		rawItems, ok := payload["data_relationships"].([]any)
		if !ok {
			t.Fatalf("data_relationships = %T, want []map[string]any or []any", payload["data_relationships"])
		}
		items = make([]map[string]any, 0, len(rawItems))
		for _, rawItem := range rawItems {
			items = append(items, rawItem.(map[string]any))
		}
	}

	for _, item := range items {
		if item["type"] == relationshipType && item["source_name"] == sourceName && item["target_name"] == targetName {
			return
		}
	}
	t.Fatalf("missing relationship type=%q source=%q target=%q in %#v", relationshipType, sourceName, targetName, items)
}

func dbtAssertCoverageState(t *testing.T, payload map[string]any, want string) {
	t.Helper()

	coverage, ok := payload["data_intelligence_coverage"].(map[string]any)
	if !ok {
		t.Fatalf("data_intelligence_coverage = %T, want map[string]any", payload["data_intelligence_coverage"])
	}
	if got := coverage["state"]; got != want {
		t.Fatalf("data_intelligence_coverage.state = %#v, want %#v", got, want)
	}
}
