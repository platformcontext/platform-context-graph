package query

import (
	"database/sql/driver"
	"encoding/json"
	"net/http"
	"net/http/httptest"
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
			want: "Function getTab has method kind getter and is documented as \"Returns the active tab.\". Defined in src/app.js (javascript).",
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
