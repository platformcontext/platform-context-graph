package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestEnrichEntityResultsWithContentMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/decorators.ts", "Class", "Demo",
					int64(5), int64(20), "typescript", "class Demo<T> {}", []byte(`{"decorators":["@sealed"],"type_parameters":["T"]}`),
				},
			},
		},
	})

	handler := &EntityHandler{Content: NewContentReader(db)}
	results := []map[string]any{
		{
			"id":         "graph-1",
			"name":       "Demo",
			"labels":     []string{"Class"},
			"file_path":  "src/decorators.ts",
			"repo_id":    "repo-1",
			"language":   "typescript",
			"start_line": 5,
			"end_line":   20,
		},
	}

	got, err := handler.enrichEntityResultsWithContentMetadata(context.Background(), results, "repo-1", "Demo", 20)
	if err != nil {
		t.Fatalf("enrichEntityResultsWithContentMetadata() error = %v, want nil", err)
	}

	metadata, ok := got[0]["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][metadata] type = %T, want map[string]any", got[0]["metadata"])
	}
	decorators, ok := metadata["decorators"].([]any)
	if !ok {
		t.Fatalf("metadata[decorators] type = %T, want []any", metadata["decorators"])
	}
	if len(decorators) != 1 || decorators[0] != "@sealed" {
		t.Fatalf("metadata[decorators] = %#v, want [@sealed]", decorators)
	}
	params, ok := metadata["type_parameters"].([]any)
	if !ok {
		t.Fatalf("metadata[type_parameters] type = %T, want []any", metadata["type_parameters"])
	}
	if len(params) != 1 || params[0] != "T" {
		t.Fatalf("metadata[type_parameters] = %#v, want [T]", params)
	}
}

func TestEnrichEntityResultsWithContentMetadataSkipsUnmatchedRows(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/other.ts", "Class", "Other",
					int64(1), int64(5), "typescript", "class Other {}", []byte(`{"decorators":["@other"]}`),
				},
			},
		},
	})

	handler := &EntityHandler{Content: NewContentReader(db)}
	results := []map[string]any{
		{
			"id":         "graph-1",
			"name":       "Demo",
			"labels":     []string{"Class"},
			"file_path":  "src/decorators.ts",
			"repo_id":    "repo-1",
			"language":   "typescript",
			"start_line": 5,
			"end_line":   20,
		},
	}

	got, err := handler.enrichEntityResultsWithContentMetadata(context.Background(), results, "repo-1", "Demo", 20)
	if err != nil {
		t.Fatalf("enrichEntityResultsWithContentMetadata() error = %v, want nil", err)
	}
	if _, ok := got[0]["metadata"]; ok {
		t.Fatalf("results[0][metadata] = %#v, want metadata to remain absent", got[0]["metadata"])
	}
}
