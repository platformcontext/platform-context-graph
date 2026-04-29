package query

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetRepositoryContextOverridesOptionalAggregationCountsWithScalarQueries(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"OPTIONAL MATCH": {
					"id":               "repo-1",
					"name":             "api-node-datax",
					"path":             "/repos/api-node-datax",
					"local_path":       "/repos/api-node-datax",
					"has_remote":       false,
					"file_count":       int64(0),
					"workload_count":   int64(0),
					"platform_count":   int64(0),
					"dependency_count": int64(0),
				},
			},
			runByMatch: map[string][]map[string]any{
				"RETURN count(DISTINCT f) AS count": {
					{"count": int64(3399)},
				},
				"RETURN count(DISTINCT w) AS count": {
					{"count": int64(1)},
				},
				"RETURN count(DISTINCT p) AS count": {
					{"count": int64(4)},
				},
				"RETURN count(DISTINCT dep) AS count": {
					{"count": int64(0)},
				},
				"fn.name IN":                          {},
				"K8sResource OR":                      {},
				"f.language IS NOT NULL":              {},
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {},
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

	for key, want := range map[string]float64{
		"file_count":     3399,
		"workload_count": 1,
		"platform_count": 4,
	} {
		if got := resp[key]; got != want {
			t.Fatalf("%s = %#v, want %#v", key, got, want)
		}
	}
}
