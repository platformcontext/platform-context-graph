package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestEnrichEntityResultsWithContentMetadataTypeScriptMappedTypeAlias(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/types.ts", "TypeAlias", "ReadonlyMap",
					int64(2), int64(4), "typescript", "type ReadonlyMap<T> = { readonly [K in keyof T]: T[K] }",
					[]byte(`{"type_alias_kind":"mapped_type","type_parameters":["T"]}`),
				},
			},
		},
	})

	handler := &EntityHandler{Content: NewContentReader(db)}
	results := []map[string]any{
		{
			"id":         "graph-1",
			"name":       "ReadonlyMap",
			"labels":     []string{"TypeAlias"},
			"file_path":  "src/types.ts",
			"repo_id":    "repo-1",
			"language":   "typescript",
			"start_line": 2,
			"end_line":   4,
		},
	}

	got, err := handler.enrichEntityResultsWithContentMetadata(context.Background(), results, "repo-1", "ReadonlyMap", 20)
	if err != nil {
		t.Fatalf("enrichEntityResultsWithContentMetadata() error = %v, want nil", err)
	}

	if gotValue, want := got[0]["semantic_summary"], "TypeAlias ReadonlyMap is a mapped type and declares type parameters T."; gotValue != want {
		t.Fatalf("results[0][semantic_summary] = %#v, want %#v", gotValue, want)
	}

	semanticProfile, ok := got[0]["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][semantic_profile] type = %T, want map[string]any", got[0]["semantic_profile"])
	}
	if gotValue, want := semanticProfile["surface_kind"], "mapped_type_alias"; gotValue != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", gotValue, want)
	}
	if gotValue, want := semanticProfile["type_alias_kind"], "mapped_type"; gotValue != want {
		t.Fatalf("semantic_profile[type_alias_kind] = %#v, want %#v", gotValue, want)
	}
}

func TestEnrichEntityResultsWithContentMetadataTypeScriptNamespaceModule(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/types.ts", "Module", "API",
					int64(1), int64(8), "typescript", "namespace API { }",
					[]byte(`{"module_kind":"namespace"}`),
				},
			},
		},
	})

	handler := &EntityHandler{Content: NewContentReader(db)}
	results := []map[string]any{
		{
			"id":         "graph-1",
			"name":       "API",
			"labels":     []string{"Module"},
			"file_path":  "src/types.ts",
			"repo_id":    "repo-1",
			"language":   "typescript",
			"start_line": 1,
			"end_line":   8,
		},
	}

	got, err := handler.enrichEntityResultsWithContentMetadata(context.Background(), results, "repo-1", "API", 20)
	if err != nil {
		t.Fatalf("enrichEntityResultsWithContentMetadata() error = %v, want nil", err)
	}

	if gotValue, want := got[0]["semantic_summary"], "Module API is a namespace."; gotValue != want {
		t.Fatalf("results[0][semantic_summary] = %#v, want %#v", gotValue, want)
	}

	semanticProfile, ok := got[0]["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][semantic_profile] type = %T, want map[string]any", got[0]["semantic_profile"])
	}
	if gotValue, want := semanticProfile["surface_kind"], "namespace_module"; gotValue != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", gotValue, want)
	}
}
