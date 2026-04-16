package query

import (
	"context"
	"database/sql/driver"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestAttachSemanticSummaryAddsStoryForSemanticEntities(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name   string
		entity map[string]any
		want   string
	}{
		{
			name: "javascript function",
			entity: map[string]any{
				"labels":    []string{"Function"},
				"name":      "getTab",
				"language":  "javascript",
				"file_path": "src/app.js",
				"metadata": map[string]any{
					"docstring":   "Returns the active tab.",
					"method_kind": "getter",
				},
			},
			want: "Function getTab has JavaScript method kind getter and is documented as \"Returns the active tab.\". Defined in src/app.js (javascript).",
		},
		{
			name: "typescript generic class",
			entity: map[string]any{
				"labels":    []string{"Class"},
				"name":      "Demo",
				"language":  "typescript",
				"file_path": "src/decorators.ts",
				"metadata": map[string]any{
					"decorators":      []any{"@sealed"},
					"type_parameters": []any{"T"},
				},
			},
			want: "Class Demo uses decorators @sealed and declares type parameters T. Defined in src/decorators.ts (typescript).",
		},
		{
			name: "tsx component",
			entity: map[string]any{
				"labels":    []string{"Component"},
				"name":      "Button",
				"language":  "tsx",
				"file_path": "src/Button.tsx",
				"metadata": map[string]any{
					"framework": "react",
				},
			},
			want: "Component Button is associated with the react framework. Defined in src/Button.tsx (tsx).",
		},
		{
			name: "python async decorator function",
			entity: map[string]any{
				"labels":    []string{"Function"},
				"name":      "handler",
				"language":  "python",
				"file_path": "src/app.py",
				"metadata": map[string]any{
					"decorators": []any{"@route"},
					"async":      true,
				},
			},
			want: "Function handler is async and uses decorators @route. Defined in src/app.py (python).",
		},
		{
			name: "python class metaclass",
			entity: map[string]any{
				"labels":    []string{"Class"},
				"name":      "Logged",
				"language":  "python",
				"file_path": "src/models.py",
				"metadata": map[string]any{
					"metaclass": "MetaLogger",
				},
			},
			want: "Class Logged uses metaclass MetaLogger. Defined in src/models.py (python).",
		},
		{
			name: "python class docstring",
			entity: map[string]any{
				"labels":    []string{"Class"},
				"name":      "Logged",
				"language":  "python",
				"file_path": "src/models.py",
				"metadata": map[string]any{
					"docstring": "Represents a configured logger.",
				},
			},
			want: "Class Logged is documented as \"Represents a configured logger.\". Defined in src/models.py (python).",
		},
		{
			name: "python type annotation",
			entity: map[string]any{
				"labels":    []string{"TypeAnnotation"},
				"name":      "name",
				"language":  "python",
				"file_path": "src/app.py",
				"metadata": map[string]any{
					"type":            "str",
					"annotation_kind": "parameter",
					"context":         "greet",
				},
			},
			want: "TypeAnnotation name is a parameter annotation for greet with type str. Defined in src/app.py (python).",
		},
		{
			name: "java applied annotation",
			entity: map[string]any{
				"labels":    []string{"Annotation"},
				"name":      "Logged",
				"language":  "java",
				"file_path": "src/Logged.java",
				"metadata": map[string]any{
					"kind":        "applied",
					"target_kind": "method_declaration",
				},
			},
			want: "Annotation Logged is applied to a method declaration. Defined in src/Logged.java (java).",
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			attachSemanticSummary(tt.entity)
			if got := StringVal(tt.entity, "story"); got != tt.want {
				t.Fatalf("story = %q, want %q", got, tt.want)
			}
		})
	}
}

func TestGetEntityContextFallsBackToContentEntitiesIncludesStory(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"component-1", "repo-1", "src/Button.tsx", "Component", "Button",
					int64(1), int64(12), "tsx", "export function Button() {}", []byte(`{"framework":"react"}`),
				},
			},
		},
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"function-1", "repo-1", "src/App.tsx", "Function", "renderApp",
					int64(5), int64(20), "tsx", "return <Button />", []byte(`{"jsx_component_usage":["Button"]}`),
				},
			},
		},
	})

	handler := &EntityHandler{Content: NewContentReader(db)}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/component-1/context", nil)
	req.SetPathValue("entity_id", "component-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["story"], "Component Button is associated with the react framework. Defined in src/Button.tsx (tsx)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
}

func TestGetEntityContextUsesGraphJavaScriptMetadataWithoutContent(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "function-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				if want := "e.docstring as docstring"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				return map[string]any{
					"id":            "function-1",
					"labels":        []any{"Function"},
					"name":          "getTab",
					"file_path":     "src/app.js",
					"language":      "javascript",
					"start_line":    int64(10),
					"end_line":      int64(24),
					"repo_id":       "repo-1",
					"repo_name":     "repo-1",
					"docstring":     "Returns the active tab.",
					"method_kind":   "getter",
					"relationships": []any{},
				}, nil
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/function-1/context", nil)
	req.SetPathValue("entity_id", "function-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["semantic_summary"], "Function getTab has JavaScript method kind getter and is documented as \"Returns the active tab.\"."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
	if got, want := resp["story"], "Function getTab has JavaScript method kind getter and is documented as \"Returns the active tab.\". Defined in src/app.js (javascript)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
	profile, ok := resp["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("resp[semantic_profile] type = %T, want map[string]any", resp["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "javascript_method"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, want := profile["method_kind"], "getter"; got != want {
		t.Fatalf("semantic_profile[method_kind] = %#v, want %#v", got, want)
	}
	jsSemantics, ok := resp["javascript_semantics"].(map[string]any)
	if !ok {
		t.Fatalf("resp[javascript_semantics] type = %T, want map[string]any", resp["javascript_semantics"])
	}
	if got, want := jsSemantics["method_kind"], "getter"; got != want {
		t.Fatalf("javascript_semantics[method_kind] = %#v, want %#v", got, want)
	}
	if got, want := jsSemantics["docstring"], "Returns the active tab."; got != want {
		t.Fatalf("javascript_semantics[docstring] = %#v, want %#v", got, want)
	}
}

func TestGetEntityContextUsesGraphPythonMetadataWithoutContent(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"content-1", "repo-1", "src/app.py", "Function", "handler",
					int64(10), int64(24), "python", "async def handler(): ...", []byte(`{"decorators":["@content"],"async":false}`),
				},
			},
		},
	})

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "function-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				if want := "e.docstring as docstring"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				return map[string]any{
					"id":            "function-1",
					"labels":        []any{"Function"},
					"name":          "handler",
					"file_path":     "src/app.py",
					"language":      "python",
					"start_line":    int64(10),
					"end_line":      int64(24),
					"repo_id":       "repo-1",
					"repo_name":     "repo-1",
					"decorators":    []any{"@route"},
					"async":         true,
					"relationships": []any{},
				}, nil
			},
		},
		Content: NewContentReader(db),
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/function-1/context", nil)
	req.SetPathValue("entity_id", "function-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["semantic_summary"], "Function handler is async and uses decorators @route."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
	if got, want := resp["story"], "Function handler is async and uses decorators @route. Defined in src/app.py (python)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
	profile, ok := resp["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("resp[semantic_profile] type = %T, want map[string]any", resp["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "decorated_async_function"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, want := profile["async"], true; got != want {
		t.Fatalf("semantic_profile[async] = %#v, want %#v", got, want)
	}
	decorators, ok := profile["decorators"].([]any)
	if !ok {
		t.Fatalf("semantic_profile[decorators] type = %T, want []any", profile["decorators"])
	}
	if len(decorators) != 1 || decorators[0] != "@route" {
		t.Fatalf("semantic_profile[decorators] = %#v, want [@route]", decorators)
	}
}

func TestGetEntityContextUsesGraphPythonTypeAnnotationWithoutContent(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "type-ann-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				if want := "e.annotation_kind as annotation_kind"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				return map[string]any{
					"id":              "type-ann-1",
					"labels":          []any{"TypeAnnotation"},
					"name":            "name",
					"file_path":       "src/app.py",
					"language":        "python",
					"start_line":      int64(10),
					"end_line":        int64(10),
					"repo_id":         "repo-1",
					"repo_name":       "repo-1",
					"annotation_kind": "parameter",
					"context":         "greet",
					"type":            "str",
					"relationships":   []any{},
				}, nil
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/type-ann-1/context", nil)
	req.SetPathValue("entity_id", "type-ann-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["semantic_summary"], "TypeAnnotation name is a parameter annotation for greet with type str."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
	if got, want := resp["story"], "TypeAnnotation name is a parameter annotation for greet with type str. Defined in src/app.py (python)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
	profile, ok := resp["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("resp[semantic_profile] type = %T, want map[string]any", resp["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "parameter_type_annotation"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, want := profile["annotation_kind"], "parameter"; got != want {
		t.Fatalf("semantic_profile[annotation_kind] = %#v, want %#v", got, want)
	}
}

func TestGetEntityContextUsesGraphPythonClassDocstringWithoutContent(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "class-docstring-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				if want := "e.docstring as docstring"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				return map[string]any{
					"id":            "class-docstring-1",
					"labels":        []any{"Class"},
					"name":          "Logged",
					"file_path":     "src/models.py",
					"language":      "python",
					"start_line":    int64(4),
					"end_line":      int64(8),
					"repo_id":       "repo-1",
					"repo_name":     "repo-1",
					"docstring":     "Represents a configured logger.",
					"relationships": []any{},
				}, nil
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/class-docstring-1/context", nil)
	req.SetPathValue("entity_id", "class-docstring-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["semantic_summary"], "Class Logged is documented as \"Represents a configured logger.\"."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
	if got, want := resp["story"], "Class Logged is documented as \"Represents a configured logger.\". Defined in src/models.py (python)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
	profile, ok := resp["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("resp[semantic_profile] type = %T, want map[string]any", resp["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "documented_class"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, want := profile["docstring"], "Represents a configured logger."; got != want {
		t.Fatalf("semantic_profile[docstring] = %#v, want %#v", got, want)
	}
}

func TestGetEntityContextUsesGraphPythonTypeAnnotationsWithoutContent(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "function-annotations-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				if want := "e.type_annotation_count as type_annotation_count"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				if want := "e.type_annotation_kinds as type_annotation_kinds"; !strings.Contains(cypher, want) {
					t.Fatalf("cypher = %q, want %q", cypher, want)
				}
				return map[string]any{
					"id":                    "function-annotations-1",
					"labels":                []any{"Function"},
					"name":                  "greet",
					"file_path":             "src/app.py",
					"language":              "python",
					"start_line":            int64(10),
					"end_line":              int64(24),
					"repo_id":               "repo-1",
					"repo_name":             "repo-1",
					"type_annotation_count": int64(2),
					"type_annotation_kinds": []any{"parameter", "return"},
					"relationships":         []any{},
				}, nil
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/entities/function-annotations-1/context", nil)
	req.SetPathValue("entity_id", "function-annotations-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d body=%s", w.Code, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v, want nil", err)
	}

	if got, want := resp["semantic_summary"], "Function greet has parameter and return type annotations."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
	if got, want := resp["story"], "Function greet has parameter and return type annotations. Defined in src/app.py (python)."; got != want {
		t.Fatalf("resp[story] = %#v, want %#v", got, want)
	}
	profile, ok := resp["semantic_profile"].(map[string]any)
	if !ok {
		t.Fatalf("resp[semantic_profile] type = %T, want map[string]any", resp["semantic_profile"])
	}
	if got, want := profile["surface_kind"], "type_annotation"; got != want {
		t.Fatalf("semantic_profile[surface_kind] = %#v, want %#v", got, want)
	}
	if got, ok := profile["type_annotation_count"].(float64); !ok || int(got) != 2 {
		t.Fatalf("semantic_profile[type_annotation_count] = %#v, want 2", profile["type_annotation_count"])
	}
	kinds, ok := profile["type_annotation_kinds"].([]any)
	if !ok {
		t.Fatalf("semantic_profile[type_annotation_kinds] type = %T, want []any", profile["type_annotation_kinds"])
	}
	if len(kinds) != 2 || kinds[0] != "parameter" || kinds[1] != "return" {
		t.Fatalf("semantic_profile[type_annotation_kinds] = %#v, want [parameter return]", kinds)
	}
}
