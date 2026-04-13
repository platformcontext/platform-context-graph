package parser

import (
	"path/filepath"
	"reflect"
	"testing"
)

func TestDefaultEngineParsePathJSONDBTManifest(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "manifest.json")
	writeTestFile(
		t,
		filePath,
		`{
  "metadata": {
    "adapter_type": "postgres",
    "project_name": "jaffle_shop"
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
      "compiled_path": "target/compiled/jaffle_shop/models/marts/order_metrics.sql",
      "relation_name": "analytics.public.order_metrics",
      "config": {
        "materialized": "view"
      },
      "depends_on": {
        "nodes": [
          "source.jaffle_shop.raw.orders",
          "source.jaffle_shop.raw.customers"
        ]
      },
      "compiled_code": "select o.id as order_id, c.full_name as customer_name from raw.public.orders o join raw.public.customers c on c.id = o.customer_id",
      "columns": {
        "order_id": {
          "name": "order_id"
        },
        "customer_name": {
          "name": "customer_name"
        }
      }
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
        "id": {
          "name": "id"
        },
        "customer_id": {
          "name": "customer_id"
        }
      }
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
        "id": {
          "name": "id"
        },
        "full_name": {
          "name": "full_name"
        }
      }
    }
  }
}`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got, want := bucketNames(t, got, "analytics_models"), []string{"order_metrics"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("analytics models = %#v, want %#v", got, want)
	}
	if got, want := bucketNames(t, got, "data_assets"), []string{
		"analytics.public.order_metrics",
		"raw.public.customers",
		"raw.public.orders",
	}; !reflect.DeepEqual(got, want) {
		t.Fatalf("data assets = %#v, want %#v", got, want)
	}
	assertRelationshipPresent(t, got, "COMPILES_TO", "order_metrics", "analytics.public.order_metrics")
	assertRelationshipPresent(t, got, "COLUMN_DERIVES_FROM", "analytics.public.order_metrics.customer_name", "raw.public.customers.full_name")
	assertCoverageState(t, got, "complete")
}

func TestDefaultEngineParsePathJSONDBTManifestFixtureVariant(t *testing.T) {
	t.Parallel()

	filePath := repoFixturePath("ecosystems", "analytics_compiled_comprehensive", "dbt_manifest.json")
	repoRoot := filepath.Dir(filePath)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got, want := bucketNames(t, got, "analytics_models"), []string{"order_metrics", "orders_expanded"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("analytics models = %#v, want %#v", got, want)
	}
	assertRelationshipPresent(t, got, "COLUMN_DERIVES_FROM", "analytics.public.orders_expanded.id", "raw.public.orders.id")
	assertCoverageState(t, got, "partial")
	assertCoverageUnresolvedReferencePresent(t, got, "sum(p.amount)", "order_metrics", "aggregate_expression_semantics_not_captured")
}

func assertCoverageUnresolvedReferencePresent(
	t *testing.T,
	payload map[string]any,
	expression string,
	modelName string,
	reason string,
) {
	t.Helper()

	coverage, ok := payload["data_intelligence_coverage"].(map[string]any)
	if !ok {
		t.Fatalf("data_intelligence_coverage = %T, want map[string]any", payload["data_intelligence_coverage"])
	}
	unresolved, ok := coverage["unresolved_references"].([]any)
	if !ok {
		t.Fatalf("data_intelligence_coverage.unresolved_references = %T, want []any", coverage["unresolved_references"])
	}
	for _, rawItem := range unresolved {
		item, ok := rawItem.(map[string]any)
		if !ok {
			continue
		}
		if item["expression"] == expression && item["model_name"] == modelName && item["reason"] == reason {
			return
		}
	}
	t.Fatalf("missing unresolved reference expression=%q model=%q reason=%q in %#v", expression, modelName, reason, unresolved)
}
