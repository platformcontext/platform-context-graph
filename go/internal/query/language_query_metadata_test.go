package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestEnrichLanguageResultsWithContentMetadata(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/handler.py", "Function", "handler",
					int64(12), int64(20), "python", "async def handler(): ...", []byte(`{"decorators":["@route"],"async":true}`),
				},
			},
		},
	})

	handler := &LanguageQueryHandler{Content: NewContentReader(db)}
	graphResults := []map[string]any{
		{
			"entity_id":  "graph-1",
			"name":       "handler",
			"labels":     []string{"Function"},
			"file_path":  "src/handler.py",
			"repo_id":    "repo-1",
			"language":   "python",
			"start_line": 12,
			"end_line":   20,
		},
	}

	got, err := handler.enrichLanguageResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"python",
		"Function",
		"handler",
		"repo-1",
		10,
	)
	if err != nil {
		t.Fatalf("enrichLanguageResultsWithContentMetadata() error = %v, want nil", err)
	}

	metadata, ok := got[0]["metadata"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][metadata] type = %T, want map[string]any", got[0]["metadata"])
	}
	if gotValue, want := metadata["async"], true; gotValue != want {
		t.Fatalf("metadata[async] = %#v, want %#v", gotValue, want)
	}
	decorators, ok := metadata["decorators"].([]any)
	if !ok {
		t.Fatalf("metadata[decorators] type = %T, want []any", metadata["decorators"])
	}
	if len(decorators) != 1 || decorators[0] != "@route" {
		t.Fatalf("metadata[decorators] = %#v, want [@route]", decorators)
	}
	if gotValue, want := got[0]["semantic_summary"], "Function handler is async and uses decorators @route."; gotValue != want {
		t.Fatalf("results[0][semantic_summary] = %#v, want %#v", gotValue, want)
	}
	semanticProfile, ok := got[0]["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][semantic_profile] type = %T, want map[string]any", got[0]["semantic_profile"])
	}
	if gotValue, want := semanticProfile["surface_kind"], "decorated_async_function"; gotValue != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", gotValue, want)
	}
	if gotValue, want := semanticProfile["async"], true; gotValue != want {
		t.Fatalf("semantic_profile[async] = %#v, want %#v", gotValue, want)
	}
	decoratorValues, ok := semanticProfile["decorators"].([]string)
	if !ok {
		t.Fatalf("semantic_profile[decorators] type = %T, want []string", semanticProfile["decorators"])
	}
	if len(decoratorValues) != 1 || decoratorValues[0] != "@route" {
		t.Fatalf("semantic_profile[decorators] = %#v, want [@route]", decoratorValues)
	}
}

func TestEnrichLanguageResultsWithContentMetadataSkipsUnmatchedRows(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/other.py", "Function", "other",
					int64(1), int64(5), "python", "def other(): pass", []byte(`{"decorators":["@cached"]}`),
				},
			},
		},
	})

	handler := &LanguageQueryHandler{Content: NewContentReader(db)}
	graphResults := []map[string]any{
		{
			"entity_id":  "graph-1",
			"name":       "handler",
			"labels":     []string{"Function"},
			"file_path":  "src/handler.py",
			"repo_id":    "repo-1",
			"language":   "python",
			"start_line": 12,
			"end_line":   20,
		},
	}

	got, err := handler.enrichLanguageResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"python",
		"Function",
		"handler",
		"repo-1",
		10,
	)
	if err != nil {
		t.Fatalf("enrichLanguageResultsWithContentMetadata() error = %v, want nil", err)
	}
	if _, ok := got[0]["metadata"]; ok {
		t.Fatalf("results[0][metadata] = %#v, want metadata to remain absent", got[0]["metadata"])
	}
	if _, ok := got[0]["semantic_summary"]; ok {
		t.Fatalf("results[0][semantic_summary] = %#v, want semantic summary to remain absent", got[0]["semantic_summary"])
	}
	if _, ok := got[0]["semantic_profile"]; ok {
		t.Fatalf("results[0][semantic_profile] = %#v, want semantic profile to remain absent", got[0]["semantic_profile"])
	}
}
