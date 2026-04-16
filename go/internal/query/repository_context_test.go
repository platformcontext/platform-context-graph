package query

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// fakeRepoGraphReader dispatches Neo4j queries to per-query stubs based on
// Cypher content matching. This lets each test control the data for every
// query in getRepositoryContext independently.
type fakeRepoGraphReader struct {
	// runSingleByMatch maps a Cypher fragment to the result row.
	runSingleByMatch map[string]map[string]any
	// runByMatch maps a Cypher fragment to multiple result rows.
	runByMatch map[string][]map[string]any
}

func (f fakeRepoGraphReader) Run(ctx context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
	for fragment, rows := range f.runByMatch {
		if strings.Contains(cypher, fragment) {
			return rows, nil
		}
	}
	return nil, nil
}

func (f fakeRepoGraphReader) RunSingle(ctx context.Context, cypher string, params map[string]any) (map[string]any, error) {
	for fragment, row := range f.runSingleByMatch {
		if strings.Contains(cypher, fragment) {
			return row, nil
		}
	}
	return nil, nil
}

func TestGetRepositoryContextReturnsEnrichedResponse(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{
				// Base repo query — must return repo + counts
				"count(DISTINCT f) as file_count": {
					"id":               "repo-1",
					"name":             "order-service",
					"path":             "/repos/order-service",
					"local_path":       "/repos/order-service",
					"remote_url":       "https://github.com/org/order-service",
					"repo_slug":        "org/order-service",
					"has_remote":       true,
					"file_count":       int64(120),
					"workload_count":   int64(2),
					"platform_count":   int64(1),
					"dependency_count": int64(3),
				},
			},
			runByMatch: map[string][]map[string]any{
				// Entry points query
				"fn.name IN": {
					{
						"name":          "main",
						"relative_path": "cmd/server/main.go",
						"language":      "go",
					},
					{
						"name":          "handler",
						"relative_path": "internal/api/handler.go",
						"language":      "go",
					},
				},
				// Infrastructure entities query
				"K8sResource OR": {
					{
						"type":      "K8sResource",
						"name":      "order-deployment",
						"kind":      "Deployment",
						"file_path": "k8s/deployment.yaml",
					},
				},
				// Language distribution query
				"f.language IS NOT NULL": {
					{
						"language":   "go",
						"file_count": int64(80),
					},
					{
						"language":   "yaml",
						"file_count": int64(30),
					},
					{
						"language":   "dockerfile",
						"file_count": int64(10),
					},
				},
				// Cross-repo relationships (outgoing)
				"DEPENDS_ON|DEPLOYS_FROM": {
					{
						"type":          "DEPENDS_ON",
						"target_name":   "auth-service",
						"target_id":     "repo-2",
						"evidence_type": "terraform_module_source",
					},
					{
						"type":          "DEPLOYS_FROM",
						"target_name":   "infra-configs",
						"target_id":     "repo-3",
						"evidence_type": "argocd_source",
					},
				},
				// Consumer repositories (incoming)
				"consumer:Repository": {
					{
						"consumer_name": "checkout-service",
						"consumer_id":   "repo-4",
					},
				},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/repositories/repo-1/context", nil)
	req.SetPathValue("repo_id", "repo-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	// Verify base repository ref
	repo, ok := resp["repository"].(map[string]any)
	if !ok {
		t.Fatalf("resp[repository] type = %T, want map", resp["repository"])
	}
	if got, want := repo["id"], "repo-1"; got != want {
		t.Fatalf("repository.id = %v, want %v", got, want)
	}

	// Verify counts preserved
	if got, want := resp["file_count"], float64(120); got != want {
		t.Fatalf("file_count = %v, want %v", got, want)
	}
	if got, want := resp["workload_count"], float64(2); got != want {
		t.Fatalf("workload_count = %v, want %v", got, want)
	}
	if got, want := resp["dependency_count"], float64(3); got != want {
		t.Fatalf("dependency_count = %v, want %v", got, want)
	}

	// Verify entry points
	entryPoints, ok := resp["entry_points"].([]any)
	if !ok {
		t.Fatalf("entry_points type = %T, want []any", resp["entry_points"])
	}
	if len(entryPoints) != 2 {
		t.Fatalf("len(entry_points) = %d, want 2", len(entryPoints))
	}
	ep0, ok := entryPoints[0].(map[string]any)
	if !ok {
		t.Fatalf("entry_points[0] type = %T", entryPoints[0])
	}
	if got, want := ep0["name"], "main"; got != want {
		t.Fatalf("entry_points[0].name = %v, want %v", got, want)
	}

	// Verify infrastructure entities
	infraEntities, ok := resp["infrastructure"].([]any)
	if !ok {
		t.Fatalf("infrastructure type = %T, want []any", resp["infrastructure"])
	}
	if len(infraEntities) != 1 {
		t.Fatalf("len(infrastructure) = %d, want 1", len(infraEntities))
	}
	infra0, ok := infraEntities[0].(map[string]any)
	if !ok {
		t.Fatalf("infrastructure[0] type = %T", infraEntities[0])
	}
	if got, want := infra0["type"], "K8sResource"; got != want {
		t.Fatalf("infrastructure[0].type = %v, want %v", got, want)
	}

	// Verify language distribution
	languages, ok := resp["languages"].([]any)
	if !ok {
		t.Fatalf("languages type = %T, want []any", resp["languages"])
	}
	if len(languages) != 3 {
		t.Fatalf("len(languages) = %d, want 3", len(languages))
	}

	// Verify cross-repo relationships
	relationships, ok := resp["relationships"].([]any)
	if !ok {
		t.Fatalf("relationships type = %T, want []any", resp["relationships"])
	}
	if len(relationships) != 2 {
		t.Fatalf("len(relationships) = %d, want 2", len(relationships))
	}
	rel0, ok := relationships[0].(map[string]any)
	if !ok {
		t.Fatalf("relationships[0] type = %T", relationships[0])
	}
	if got, want := rel0["type"], "DEPENDS_ON"; got != want {
		t.Fatalf("relationships[0].type = %v, want %v", got, want)
	}
	if got, want := rel0["target_name"], "auth-service"; got != want {
		t.Fatalf("relationships[0].target_name = %v, want %v", got, want)
	}

	// Verify consumer repositories
	consumers, ok := resp["consumers"].([]any)
	if !ok {
		t.Fatalf("consumers type = %T, want []any", resp["consumers"])
	}
	if len(consumers) != 1 {
		t.Fatalf("len(consumers) = %d, want 1", len(consumers))
	}
	con0, ok := consumers[0].(map[string]any)
	if !ok {
		t.Fatalf("consumers[0] type = %T", consumers[0])
	}
	if got, want := con0["name"], "checkout-service"; got != want {
		t.Fatalf("consumers[0].name = %v, want %v", got, want)
	}
}

func TestGetRepositoryContextReturnsNotFoundForMissingRepo(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{},
			runByMatch:       map[string][]map[string]any{},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/repositories/unknown/context", nil)
	req.SetPathValue("repo_id", "unknown")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusNotFound; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}
}

func TestGetRepositoryContextHandlesEmptyEnrichmentGracefully(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"count(DISTINCT f) as file_count": {
					"id":               "repo-empty",
					"name":             "empty-repo",
					"path":             "/repos/empty-repo",
					"local_path":       "/repos/empty-repo",
					"has_remote":       false,
					"file_count":       int64(0),
					"workload_count":   int64(0),
					"platform_count":   int64(0),
					"dependency_count": int64(0),
				},
			},
			runByMatch: map[string][]map[string]any{},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/repositories/repo-empty/context", nil)
	req.SetPathValue("repo_id", "repo-empty")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	// All enrichment sections should be empty slices, not nil
	for _, key := range []string{"entry_points", "infrastructure", "languages", "relationships", "consumers"} {
		val, ok := resp[key].([]any)
		if !ok {
			t.Fatalf("resp[%s] type = %T, want []any", key, resp[key])
		}
		if len(val) != 0 {
			t.Fatalf("len(resp[%s]) = %d, want 0", key, len(val))
		}
	}
}
