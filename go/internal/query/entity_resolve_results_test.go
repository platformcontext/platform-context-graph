package query

import (
	"bytes"
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestResolveEntityRanksCanonicalServiceEntitiesAheadOfAnonymousDirectories(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeGraphReader{
			run: func(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
				if got, want := params["name"], "service-edge-api"; got != want {
					t.Fatalf("params[name] = %#v, want %#v", got, want)
				}
				return []map[string]any{
					{
						"id":     "",
						"labels": []any{"Directory"},
						"name":   "service-edge-api",
					},
					{
						"id":         "content-entity:e_chart",
						"labels":     []any{"HelmChart"},
						"name":       "service-edge-api",
						"file_path":  "charts/service-edge-api/Chart.yaml",
						"repo_id":    "repository:r_helm",
						"repo_name":  "deployment-helm",
						"language":   "yaml",
						"start_line": int64(1),
						"end_line":   int64(8),
					},
					{
						"id":        "repository:r_service_edge_api",
						"labels":    []any{"Repository"},
						"name":      "service-edge-api",
						"repo_id":   "",
						"repo_name": "",
					},
					{
						"id":     "workload:service-edge-api",
						"labels": []any{"Workload"},
						"name":   "service-edge-api",
					},
					{
						"id":     "workload-instance:service-edge-api:modern",
						"labels": []any{"WorkloadInstance"},
						"name":   "service-edge-api",
					},
					{
						"id":     "",
						"labels": []any{"Directory"},
						"name":   "service-edge-api",
					},
				}, nil
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/entities/resolve",
		bytes.NewBufferString(`{"name":"service-edge-api"}`),
	)
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d body=%s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal() error = %v", err)
	}
	entities, ok := resp["entities"].([]any)
	if !ok {
		t.Fatalf("entities type = %T, want []any", resp["entities"])
	}
	if got, want := len(entities), 4; got != want {
		t.Fatalf("len(entities) = %d, want %d", got, want)
	}

	first, _ := entities[0].(map[string]any)
	second, _ := entities[1].(map[string]any)
	third, _ := entities[2].(map[string]any)
	if got, want := first["id"], "repository:r_service_edge_api"; got != want {
		t.Fatalf("entities[0].id = %#v, want %#v", got, want)
	}
	if got, want := second["id"], "workload:service-edge-api"; got != want {
		t.Fatalf("entities[1].id = %#v, want %#v", got, want)
	}
	if got, want := third["id"], "workload-instance:service-edge-api:modern"; got != want {
		t.Fatalf("entities[2].id = %#v, want %#v", got, want)
	}

	for _, raw := range entities {
		entity, _ := raw.(map[string]any)
		if gotID, gotRepoID, gotFile := entity["id"], entity["repo_id"], entity["file_path"]; gotID == "" && gotRepoID == "" && gotFile == "" {
			t.Fatalf("anonymous entity leaked into response: %#v", entity)
		}
	}
}
