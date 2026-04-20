package query

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

type selectorAwareRepoGraphReader struct{}

func (selectorAwareRepoGraphReader) RunSingle(_ context.Context, cypher string, params map[string]any) (map[string]any, error) {
	if !strings.Contains(cypher, "WHERE r.id = $repo_selector OR r.name = $repo_selector") {
		return nil, nil
	}
	if got, want := params["repo_selector"], "order-service"; got != want {
		return nil, nil
	}
	return map[string]any{
		"id":               "repo-1",
		"name":             "order-service",
		"path":             "/repos/order-service",
		"local_path":       "/repos/order-service",
		"remote_url":       "https://github.com/org/order-service",
		"repo_slug":        "org/order-service",
		"has_remote":       true,
		"file_count":       int64(12),
		"workload_count":   int64(1),
		"platform_count":   int64(1),
		"dependency_count": int64(1),
	}, nil
}

func (selectorAwareRepoGraphReader) Run(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
	if got, want := params["repo_id"], "repo-1"; got != want {
		return nil, nil
	}
	switch {
	case strings.Contains(cypher, "fn.name IN"):
		return []map[string]any{
			{
				"name":          "main",
				"relative_path": "cmd/server/main.go",
				"language":      "go",
			},
		}, nil
	case strings.Contains(cypher, "f.language IS NOT NULL"):
		return []map[string]any{
			{
				"language":   "go",
				"file_count": int64(12),
			},
		}, nil
	default:
		return nil, nil
	}
}

func TestGetRepositoryContextAcceptsRepositoryNameSelector(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{Neo4j: selectorAwareRepoGraphReader{}}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/repositories/order-service/context", nil)
	req.SetPathValue("repo_id", "order-service")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	repo, ok := resp["repository"].(map[string]any)
	if !ok {
		t.Fatalf("resp[repository] type = %T, want map[string]any", resp["repository"])
	}
	if got, want := repo["id"], "repo-1"; got != want {
		t.Fatalf("repository.id = %v, want %v", got, want)
	}

	entryPoints, ok := resp["entry_points"].([]any)
	if !ok {
		t.Fatalf("entry_points type = %T, want []any", resp["entry_points"])
	}
	if len(entryPoints) != 1 {
		t.Fatalf("len(entry_points) = %d, want 1", len(entryPoints))
	}

	languages, ok := resp["languages"].([]any)
	if !ok {
		t.Fatalf("languages type = %T, want []any", resp["languages"])
	}
	if len(languages) != 1 {
		t.Fatalf("len(languages) = %d, want 1", len(languages))
	}
}
