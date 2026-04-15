package query

import (
	"context"
	"database/sql/driver"
	"testing"
)

func TestExtractJavaScriptSemantics(t *testing.T) {
	t.Parallel()

	semantics := ExtractJavaScriptSemantics(map[string]any{
		"docstring":   "Returns the active tab.",
		"method_kind": "getter",
	})

	if got, want := semantics.Docstring, "Returns the active tab."; got != want {
		t.Fatalf("Docstring = %q, want %q", got, want)
	}
	if got, want := semantics.MethodKind, "getter"; got != want {
		t.Fatalf("MethodKind = %q, want %q", got, want)
	}
	if !semantics.Present() {
		t.Fatal("Present() = false, want true")
	}
}

func TestExtractJavaScriptSemanticsSkipsMissingValues(t *testing.T) {
	t.Parallel()

	semantics := ExtractJavaScriptSemantics(map[string]any{
		"docstring":   "",
		"method_kind": nil,
	})

	if semantics.Present() {
		t.Fatal("Present() = true, want false")
	}
	if got := semantics.Fields(); len(got) != 0 {
		t.Fatalf("Fields() = %#v, want empty map", got)
	}
}

func TestAttachJavaScriptSemanticsClonesResult(t *testing.T) {
	t.Parallel()

	result := map[string]any{
		"entity_id": "graph-1",
		"name":      "getTab",
	}

	got := AttachJavaScriptSemantics(result, map[string]any{
		"docstring":   "Returns the active tab.",
		"method_kind": "getter",
	})

	if _, ok := result["javascript_semantics"]; ok {
		t.Fatal("result was mutated, want original map unchanged")
	}

	semantics, ok := got["javascript_semantics"].(map[string]any)
	if !ok {
		t.Fatalf("javascript_semantics type = %T, want map[string]any", got["javascript_semantics"])
	}
	if got, want := semantics["docstring"], "Returns the active tab."; got != want {
		t.Fatalf("javascript_semantics[docstring] = %#v, want %#v", got, want)
	}
	if got, want := semantics["method_kind"], "getter"; got != want {
		t.Fatalf("javascript_semantics[method_kind] = %#v, want %#v", got, want)
	}
}

func TestAttachJavaScriptSemanticsReturnsOriginalWhenEmpty(t *testing.T) {
	t.Parallel()

	result := map[string]any{
		"entity_id": "graph-1",
	}

	got := AttachJavaScriptSemantics(result, map[string]any{})

	if _, ok := got["javascript_semantics"]; ok {
		t.Fatal("javascript_semantics present, want absent")
	}
	if got["entity_id"] != "graph-1" {
		t.Fatalf("entity_id = %#v, want graph-1", got["entity_id"])
	}
}

func TestEnrichLanguageResultsWithContentMetadataJavaScriptMethod(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"js-fn-1", "repo-1", "src/app.js", "Function", "getTab",
					int64(10), int64(24), "javascript", "export function getTab() {}", []byte(`{"docstring":"Returns the active tab.","method_kind":"getter"}`),
				},
			},
		},
	})

	handler := &LanguageQueryHandler{Content: NewContentReader(db)}
	graphResults := []map[string]any{
		{
			"entity_id":  "graph-1",
			"name":       "getTab",
			"labels":     []string{"Function"},
			"file_path":  "src/app.js",
			"repo_id":    "repo-1",
			"language":   "javascript",
			"start_line": 10,
			"end_line":   24,
		},
	}

	got, err := handler.enrichLanguageResultsWithContentMetadata(
		context.Background(),
		graphResults,
		"javascript",
		"Function",
		"getTab",
		"repo-1",
		10,
	)
	if err != nil {
		t.Fatalf("enrichLanguageResultsWithContentMetadata() error = %v, want nil", err)
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
	if gotValue, want := semanticProfile["method_kind"], "getter"; gotValue != want {
		t.Fatalf("semantic_profile[method_kind] = %#v, want %#v", gotValue, want)
	}
}
