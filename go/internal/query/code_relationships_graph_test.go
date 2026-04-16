package query

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type fakeGraphReader struct {
	run       func(context.Context, string, map[string]any) ([]map[string]any, error)
	runSingle func(context.Context, string, map[string]any) (map[string]any, error)
}

func (f fakeGraphReader) Run(ctx context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
	if f.run == nil {
		return nil, nil
	}
	return f.run(ctx, cypher, params)
}

func (f fakeGraphReader) RunSingle(ctx context.Context, cypher string, params map[string]any) (map[string]any, error) {
	if f.runSingle != nil {
		return f.runSingle(ctx, cypher, params)
	}
	rows, err := f.Run(ctx, cypher, params)
	if err != nil || len(rows) == 0 {
		return nil, err
	}
	return rows[0], nil
}

func TestHandleRelationshipsMatchesGraphEntityByExactName(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if !strings.Contains(cypher, "WHERE e.name = $name") {
					t.Fatalf("cypher = %q, want exact name lookup", cypher)
				}
				if got, want := params["name"], "handlePayment"; got != want {
					t.Fatalf("params[name] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"id":         "function-1",
						"name":       "handlePayment",
						"labels":     []any{"Function"},
						"file_path":  "src/payments.ts",
						"repo_id":    "repo-1",
						"repo_name":  "payments",
						"language":   "typescript",
						"start_line": int64(10),
						"end_line":   int64(32),
						"outgoing": []any{
							map[string]any{
								"direction":   "outgoing",
								"type":        "CALLS",
								"target_name": "chargeCard",
								"target_id":   "function-2",
							},
						},
						"incoming": []any{},
					},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"name":"handlePayment","direction":"outgoing","relationship_type":"CALLS"}`),
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
	if got, want := resp["entity_id"], "function-1"; got != want {
		t.Fatalf("resp[entity_id] = %#v, want %#v", got, want)
	}
	outgoing, ok := resp["outgoing"].([]any)
	if !ok {
		t.Fatalf("resp[outgoing] type = %T, want []any", resp["outgoing"])
	}
	if len(outgoing) != 1 {
		t.Fatalf("len(resp[outgoing]) = %d, want 1", len(outgoing))
	}
	incoming, ok := resp["incoming"].([]any)
	if !ok {
		t.Fatalf("resp[incoming] type = %T, want []any", resp["incoming"])
	}
	if len(incoming) != 0 {
		t.Fatalf("len(resp[incoming]) = %d, want 0", len(incoming))
	}
}

func TestHandleRelationshipsNormalizesGraphBackedTSXComponentCalls(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-1",
					"name":       "renderApp",
					"labels":     []any{"Function"},
					"file_path":  "src/App.tsx",
					"repo_id":    "repo-1",
					"repo_name":  "ui",
					"language":   "tsx",
					"start_line": int64(3),
					"end_line":   int64(8),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"call_kind":   "jsx_component",
							"target_name": "ToolbarButton",
							"target_id":   "function-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"function-1","direction":"outgoing","relationship_type":"REFERENCES"}`),
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
	outgoing, ok := resp["outgoing"].([]any)
	if !ok || len(outgoing) != 1 {
		t.Fatalf("resp[outgoing] = %#v, want one normalized relationship", resp["outgoing"])
	}
	relationship, ok := outgoing[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[outgoing][0] type = %T, want map[string]any", outgoing[0])
	}
	if got, want := relationship["type"], "REFERENCES"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "jsx_component_call_kind"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_name"], "ToolbarButton"; got != want {
		t.Fatalf("relationship[target_name] = %#v, want %#v", got, want)
	}
}

func TestHandleRelationshipsReturnsGraphBackedTSXComponentReferences(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-1",
					"name":       "renderApp",
					"labels":     []any{"Function"},
					"file_path":  "src/App.tsx",
					"repo_id":    "repo-1",
					"repo_name":  "ui",
					"language":   "tsx",
					"start_line": int64(3),
					"end_line":   int64(8),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "REFERENCES",
							"call_kind":   "jsx_component",
							"reason":      "jsx_component_reference",
							"target_name": "ToolbarButton",
							"target_id":   "function-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"function-1","direction":"outgoing","relationship_type":"REFERENCES"}`),
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
	outgoing, ok := resp["outgoing"].([]any)
	if !ok || len(outgoing) != 1 {
		t.Fatalf("resp[outgoing] = %#v, want one graph-backed relationship", resp["outgoing"])
	}
	relationship, ok := outgoing[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[outgoing][0] type = %T, want map[string]any", outgoing[0])
	}
	if got, want := relationship["type"], "REFERENCES"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "jsx_component_reference"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
}

func TestHandleRelationshipsReturnsGraphBackedKotlinFunctionReturnReceiverChains(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-1",
					"name":       "usage",
					"labels":     []any{"Function"},
					"file_path":  "src/Usage.kt",
					"repo_id":    "repo-1",
					"repo_name":  "comprehensive",
					"language":   "kotlin",
					"start_line": int64(10),
					"end_line":   int64(15),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"call_kind":   "kotlin_function_return_receiver_chain",
							"target_name": "info",
							"target_id":   "function-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"function-1","direction":"outgoing","relationship_type":"CALLS"}`),
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
	if got, want := resp["language"], "kotlin"; got != want {
		t.Fatalf("resp[language] = %#v, want %#v", got, want)
	}
	outgoing, ok := resp["outgoing"].([]any)
	if !ok || len(outgoing) != 1 {
		t.Fatalf("resp[outgoing] = %#v, want one graph-backed relationship", resp["outgoing"])
	}
	relationship, ok := outgoing[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[outgoing][0] type = %T, want map[string]any", outgoing[0])
	}
	if got, want := relationship["type"], "CALLS"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["call_kind"], "kotlin_function_return_receiver_chain"; got != want {
		t.Fatalf("relationship[call_kind] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_name"], "info"; got != want {
		t.Fatalf("relationship[target_name] = %#v, want %#v", got, want)
	}
}

func TestHandleRelationshipsReturnsGraphBackedPHPObjectCallRows(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "function-php-1",
					"name":       "info",
					"labels":     []any{"Function"},
					"file_path":  "src/Service.php",
					"repo_id":    "repo-1",
					"repo_name":  "payments",
					"language":   "php",
					"start_line": int64(12),
					"end_line":   int64(18),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "CALLS",
							"call_kind":   "php_direct_free_function_return_receiver_chain",
							"reason":      "php_direct_free_function_return_receiver_chain",
							"target_name": "info",
							"target_id":   "function-php-2",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"function-php-1","direction":"outgoing","relationship_type":"CALLS"}`),
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
	if got, want := resp["language"], "php"; got != want {
		t.Fatalf("resp[language] = %#v, want %#v", got, want)
	}
	outgoing, ok := resp["outgoing"].([]any)
	if !ok || len(outgoing) != 1 {
		t.Fatalf("resp[outgoing] = %#v, want one graph-backed relationship", resp["outgoing"])
	}
	relationship, ok := outgoing[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[outgoing][0] type = %T, want map[string]any", outgoing[0])
	}
	if got, want := relationship["type"], "CALLS"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["call_kind"], "php_direct_free_function_return_receiver_chain"; got != want {
		t.Fatalf("relationship[call_kind] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "php_direct_free_function_return_receiver_chain"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_name"], "info"; got != want {
		t.Fatalf("relationship[target_name] = %#v, want %#v", got, want)
	}
	incoming, ok := resp["incoming"].([]any)
	if !ok {
		t.Fatalf("resp[incoming] type = %T, want []any", resp["incoming"])
	}
	if len(incoming) != 0 {
		t.Fatalf("len(resp[incoming]) = %d, want 0", len(incoming))
	}
}

func TestHandleRelationshipsReturnsGraphBackedTypeScriptClassWithTypeScriptSemantics(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
				if got, want := params["entity_id"], "class-ts-1"; got != want {
					t.Fatalf("params[entity_id] = %#v, want %#v", got, want)
				}
				for _, fragment := range []string{
					"e.type_parameters as type_parameters",
					"e.declaration_merge_group as declaration_merge_group",
					"e.declaration_merge_count as declaration_merge_count",
					"e.declaration_merge_kinds as declaration_merge_kinds",
					"e.decorators as decorators",
				} {
					if !strings.Contains(cypher, fragment) {
						t.Fatalf("cypher = %q, want %q", cypher, fragment)
					}
				}
				return map[string]any{
					"id":                      "class-ts-1",
					"name":                    "Service",
					"labels":                  []any{"Class"},
					"file_path":               "src/service.ts",
					"repo_id":                 "repo-1",
					"repo_name":               "repo-1",
					"language":                "typescript",
					"start_line":              int64(1),
					"end_line":                int64(12),
					"decorators":              []any{"@sealed"},
					"type_parameters":         []any{"T"},
					"declaration_merge_group": "Service",
					"declaration_merge_count": int64(2),
					"declaration_merge_kinds": []any{"class", "namespace"},
					"outgoing":                []any{},
					"incoming":                []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"class-ts-1","direction":"outgoing","relationship_type":"CALLS"}`),
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
	semantics, ok := resp["typescript_semantics"].(map[string]any)
	if !ok {
		t.Fatalf("resp[typescript_semantics] type = %T, want map[string]any", resp["typescript_semantics"])
	}
	typeParameters, ok := semantics["type_parameters"].([]any)
	if !ok {
		t.Fatalf("typescript_semantics[type_parameters] type = %T, want []any", semantics["type_parameters"])
	}
	if len(typeParameters) != 1 || typeParameters[0] != "T" {
		t.Fatalf("typescript_semantics[type_parameters] = %#v, want [T]", typeParameters)
	}
	if got, want := resp["semantic_summary"], "Class Service participates in TypeScript declaration merging with namespace Service."; got != want {
		t.Fatalf("resp[semantic_summary] = %#v, want %#v", got, want)
	}
}

func TestHandleRelationshipsReturnsGraphBackedPythonMetaclassUsesMetaclass(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			runSingle: func(_ context.Context, _ string, _ map[string]any) (map[string]any, error) {
				return map[string]any{
					"id":         "class-logged",
					"name":       "Logged",
					"labels":     []any{"Class"},
					"file_path":  "src/models.py",
					"repo_id":    "repo-1",
					"repo_name":  "service",
					"language":   "python",
					"start_line": int64(4),
					"end_line":   int64(8),
					"outgoing": []any{
						map[string]any{
							"direction":   "outgoing",
							"type":        "USES_METACLASS",
							"reason":      "Parser and symbol analysis resolved a Python metaclass edge",
							"target_name": "MetaLogger",
							"target_id":   "class-meta",
						},
					},
					"incoming": []any{},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/relationships",
		bytes.NewBufferString(`{"entity_id":"class-logged","direction":"outgoing","relationship_type":"USES_METACLASS"}`),
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
	if got, want := resp["entity_id"], "class-logged"; got != want {
		t.Fatalf("resp[entity_id] = %#v, want %#v", got, want)
	}
	outgoing, ok := resp["outgoing"].([]any)
	if !ok || len(outgoing) != 1 {
		t.Fatalf("resp[outgoing] = %#v, want one graph-backed relationship", resp["outgoing"])
	}
	relationship, ok := outgoing[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[outgoing][0] type = %T, want map[string]any", outgoing[0])
	}
	if got, want := relationship["type"], "USES_METACLASS"; got != want {
		t.Fatalf("relationship[type] = %#v, want %#v", got, want)
	}
	if got, want := relationship["reason"], "Parser and symbol analysis resolved a Python metaclass edge"; got != want {
		t.Fatalf("relationship[reason] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_name"], "MetaLogger"; got != want {
		t.Fatalf("relationship[target_name] = %#v, want %#v", got, want)
	}
	if got, want := relationship["target_id"], "class-meta"; got != want {
		t.Fatalf("relationship[target_id] = %#v, want %#v", got, want)
	}
	incoming, ok := resp["incoming"].([]any)
	if !ok {
		t.Fatalf("resp[incoming] type = %T, want []any", resp["incoming"])
	}
	if len(incoming) != 0 {
		t.Fatalf("len(resp[incoming]) = %d, want 0", len(incoming))
	}
}
