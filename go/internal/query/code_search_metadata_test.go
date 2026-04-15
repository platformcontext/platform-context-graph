package query

import (
	"bytes"
	"context"
	"database/sql/driver"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestEnrichGraphSearchResultsWithContentMetadata(t *testing.T) {
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

	handler := &CodeHandler{Content: NewContentReader(db)}
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

	got, err := handler.enrichGraphSearchResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"repo-1",
		"handler",
		10,
	)
	if err != nil {
		t.Fatalf("enrichGraphSearchResultsWithContentMetadata() error = %v, want nil", err)
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

func TestEnrichGraphSearchResultsWithContentMetadataPrefersExistingJavaScriptMetadata(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{}
	graphResults := []map[string]any{
		{
			"entity_id":  "graph-js-1",
			"name":       "getTab",
			"labels":     []string{"Function"},
			"file_path":  "src/app.js",
			"repo_id":    "repo-1",
			"language":   "javascript",
			"start_line": 10,
			"end_line":   24,
			"metadata": map[string]any{
				"docstring":   "Returns the active tab.",
				"method_kind": "getter",
			},
		},
	}

	got, err := handler.enrichGraphSearchResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"repo-1",
		"getTab",
		10,
	)
	if err != nil {
		t.Fatalf("enrichGraphSearchResultsWithContentMetadata() error = %v, want nil", err)
	}

	if gotValue, want := got[0]["semantic_summary"], "Function getTab has JavaScript method kind getter and is documented as \"Returns the active tab.\"."; gotValue != want {
		t.Fatalf("results[0][semantic_summary] = %#v, want %#v", gotValue, want)
	}
	semanticProfile, ok := got[0]["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("results[0][semantic_profile] type = %T, want map[string]any", got[0]["semantic_profile"])
	}
	if gotValue, want := semanticProfile["surface_kind"], "javascript_method"; gotValue != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", gotValue, want)
	}
}

func TestEnrichGraphSearchResultsWithContentMetadataSkipsUnmatchedRows(t *testing.T) {
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

	handler := &CodeHandler{Content: NewContentReader(db)}
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

	got, err := handler.enrichGraphSearchResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"repo-1",
		"handler",
		10,
	)
	if err != nil {
		t.Fatalf("enrichGraphSearchResultsWithContentMetadata() error = %v, want nil", err)
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

func TestHandleSearchReturnsGraphBackedJavaScriptMetadataWithoutContent(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if got, want := params["repo_id"], "repo-1"; got != want {
					t.Fatalf("params[repo_id] = %#v, want %#v", got, want)
				}
				if got, want := params["query"], "getTab"; got != want {
					t.Fatalf("params[query] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"entity_id":   "graph-js-1",
						"name":        "getTab",
						"labels":      []any{"Function"},
						"file_path":   "src/app.js",
						"repo_id":     "repo-1",
						"repo_name":   "repo-1",
						"language":    "javascript",
						"start_line":  int64(10),
						"end_line":    int64(24),
						"docstring":   "Returns the active tab.",
						"method_kind": "getter",
					},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/search",
		bytes.NewBufferString(`{"query":"getTab","repo_id":"repo-1","language":"javascript"}`),
	)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d body=%s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}
	if got, want := resp["source"], "graph"; got != want {
		t.Fatalf("resp[source] = %#v, want %#v", got, want)
	}

	results, ok := resp["results"].([]any)
	if !ok || len(results) != 1 {
		t.Fatalf("results = %#v, want one graph-backed JavaScript result", resp["results"])
	}
	result, ok := results[0].(map[string]any)
	if !ok {
		t.Fatalf("result type = %T, want map[string]any", results[0])
	}
	if got, want := result["semantic_summary"], "Function getTab has JavaScript method kind getter and is documented as \"Returns the active tab.\"."; got != want {
		t.Fatalf("result[semantic_summary] = %#v, want %#v", got, want)
	}
	profile, ok := result["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("result[semantic_profile] type = %T, want map[string]any", result["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "javascript_method"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
}
