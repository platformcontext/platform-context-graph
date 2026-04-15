package query

import (
	"bytes"
	"context"
	"database/sql/driver"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestHandleDeadCodeExcludesDecoratedEntities(t *testing.T) {
	t.Parallel()

	db := openContentReaderTestDB(t, []contentReaderQueryResult{
		{
			columns: []string{
				"entity_id", "repo_id", "relative_path", "entity_type", "entity_name",
				"start_line", "end_line", "language", "source_cache", "metadata",
			},
			rows: [][]driver.Value{
				{
					"function-1", "repo-1", "src/routes.py", "Function", "handler",
					int64(10), int64(14), "python", "def handler(): pass", []byte(`{"decorators":["@route"]}`),
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
					"function-2", "repo-1", "src/payments.py", "Function", "helper",
					int64(20), int64(30), "python", "def helper(): pass", []byte(`{"decorators":["@cached"]}`),
				},
			},
		},
	})

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if got, want := params["repo_id"], "repo-1"; got != want {
					t.Fatalf("params[repo_id] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"entity_id":  "function-1",
						"name":       "handler",
						"labels":     []any{"Function"},
						"file_path":  "src/routes.py",
						"repo_id":    "repo-1",
						"repo_name":  "payments",
						"language":   "python",
						"start_line": int64(10),
						"end_line":   int64(14),
					},
					{
						"entity_id":  "function-2",
						"name":       "helper",
						"labels":     []any{"Function"},
						"file_path":  "src/payments.py",
						"repo_id":    "repo-1",
						"repo_name":  "payments",
						"language":   "python",
						"start_line": int64(20),
						"end_line":   int64(30),
					},
				}, nil
			},
		},
		Content: NewContentReader(db),
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/dead-code",
		bytes.NewBufferString(`{"repo_id":"repo-1","exclude_decorated_with":["@route"]}`),
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
	results, ok := resp["results"].([]any)
	if !ok {
		t.Fatalf("resp[results] type = %T, want []any", resp["results"])
	}
	if got, want := len(results), 1; got != want {
		t.Fatalf("len(resp[results]) = %d, want %d", got, want)
	}
	result, ok := results[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[results][0] type = %T, want map[string]any", results[0])
	}
	if got, want := result["name"], "helper"; got != want {
		t.Fatalf("result[name] = %#v, want %#v", got, want)
	}
}

func TestHandleCallChainReturnsShortestPath(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if !strings.Contains(cypher, "shortestPath") {
					t.Fatalf("cypher = %q, want shortestPath query", cypher)
				}
				if strings.Contains(cypher, "CALLS_FUNCTION") {
					t.Fatalf("cypher = %q, want canonical CALLS edges only", cypher)
				}
				if !strings.Contains(cypher, "[:CALLS*1..6]") {
					t.Fatalf("cypher = %q, want bounded CALLS traversal", cypher)
				}
				if !strings.Contains(cypher, "start.name = $start") {
					t.Fatalf("cypher = %q, want exact start-name predicate", cypher)
				}
				if !strings.Contains(cypher, "end.name = $end") {
					t.Fatalf("cypher = %q, want exact end-name predicate", cypher)
				}
				if got, want := params["start"], "wrapper"; got != want {
					t.Fatalf("params[start] = %#v, want %#v", got, want)
				}
				if got, want := params["end"], "helper"; got != want {
					t.Fatalf("params[end] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"chain": []any{
							map[string]any{"id": "fn-1", "name": "wrapper", "labels": []any{"Function"}},
							map[string]any{"id": "fn-2", "name": "delegate", "labels": []any{"Function"}},
							map[string]any{"id": "fn-3", "name": "helper", "labels": []any{"Function"}},
						},
						"depth": int64(2),
					},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/call-chain",
		bytes.NewBufferString(`{"start":"wrapper","end":"helper","max_depth":6}`),
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
	chains, ok := resp["chains"].([]any)
	if !ok {
		t.Fatalf("resp[chains] type = %T, want []any", resp["chains"])
	}
	if got, want := len(chains), 1; got != want {
		t.Fatalf("len(resp[chains]) = %d, want %d", got, want)
	}
}

func TestHandleCallChainSupportsEntityIDAndRepoScopedLookup(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if !strings.Contains(cypher, "start.id = $start_entity_id") {
					t.Fatalf("cypher = %q, want start entity-id predicate", cypher)
				}
				if !strings.Contains(cypher, "end.id = $end_entity_id") {
					t.Fatalf("cypher = %q, want end entity-id predicate", cypher)
				}
				if !strings.Contains(cypher, "start.repo_id = $repo_id") ||
					!strings.Contains(cypher, "end.repo_id = $repo_id") {
					t.Fatalf("cypher = %q, want repo scoping for both endpoints", cypher)
				}
				if got, want := params["start_entity_id"], "fn-1"; got != want {
					t.Fatalf("params[start_entity_id] = %#v, want %#v", got, want)
				}
				if got, want := params["end_entity_id"], "fn-3"; got != want {
					t.Fatalf("params[end_entity_id] = %#v, want %#v", got, want)
				}
				if got, want := params["repo_id"], "repo-1"; got != want {
					t.Fatalf("params[repo_id] = %#v, want %#v", got, want)
				}
				if _, ok := params["start"]; ok {
					t.Fatalf("params[start] present = %#v, want omitted for entity-id lookup", params["start"])
				}
				if _, ok := params["end"]; ok {
					t.Fatalf("params[end] present = %#v, want omitted for entity-id lookup", params["end"])
				}
				return []map[string]any{
					{
						"chain": []any{
							map[string]any{"id": "fn-1", "name": "wrapper", "labels": []any{"Function"}},
							map[string]any{"id": "fn-2", "name": "delegate", "labels": []any{"Function"}},
							map[string]any{"id": "fn-3", "name": "helper", "labels": []any{"Function"}},
						},
						"depth": int64(2),
					},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/call-chain",
		bytes.NewBufferString(`{"start_entity_id":"fn-1","end_entity_id":"fn-3","repo_id":"repo-1","max_depth":4}`),
	)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d body=%s", got, want, w.Body.String())
	}
}

func TestHandleCallChainSupportsRustImplContextQualifiedLookup(t *testing.T) {
	t.Parallel()

	handler := &CodeHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if !strings.Contains(cypher, "shortestPath") {
					t.Fatalf("cypher = %q, want shortestPath query", cypher)
				}
				if strings.Contains(cypher, "CALLS_FUNCTION") {
					t.Fatalf("cypher = %q, want canonical CALLS edges only", cypher)
				}
				if !strings.Contains(cypher, "[:CALLS*1..3]") {
					t.Fatalf("cypher = %q, want bounded CALLS traversal", cypher)
				}
				if !strings.Contains(cypher, "start.id = $start_entity_id") {
					t.Fatalf("cypher = %q, want exact start entity-id predicate", cypher)
				}
				if !strings.Contains(cypher, "end.id = $end_entity_id") {
					t.Fatalf("cypher = %q, want exact end entity-id predicate", cypher)
				}
				if got, want := params["start_entity_id"], "fn-new"; got != want {
					t.Fatalf("params[start_entity_id] = %#v, want %#v", got, want)
				}
				if got, want := params["end_entity_id"], "fn-x"; got != want {
					t.Fatalf("params[end_entity_id] = %#v, want %#v", got, want)
				}
				if got, want := params["repo_id"], "repo-rust"; got != want {
					t.Fatalf("params[repo_id] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"chain": []any{
							map[string]any{"id": "fn-new", "name": "new", "labels": []any{"Function"}},
							map[string]any{"id": "fn-x", "name": "x", "labels": []any{"Function"}},
						},
						"depth": int64(1),
					},
				}, nil
			},
		},
	}
	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/code/call-chain",
		bytes.NewBufferString(`{"start_entity_id":"fn-new","end_entity_id":"fn-x","repo_id":"repo-rust","max_depth":3}`),
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
	chains, ok := resp["chains"].([]any)
	if !ok {
		t.Fatalf("resp[chains] type = %T, want []any", resp["chains"])
	}
	if got, want := len(chains), 1; got != want {
		t.Fatalf("len(resp[chains]) = %d, want %d", got, want)
	}
	chain, ok := chains[0].(map[string]any)
	if !ok {
		t.Fatalf("resp[chains][0] type = %T, want map[string]any", chains[0])
	}
	nodes, ok := chain["chain"].([]any)
	if !ok || len(nodes) != 2 {
		t.Fatalf("resp[chains][0][chain] = %#v, want two Rust impl-method nodes", chain["chain"])
	}
}
