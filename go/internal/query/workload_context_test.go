package query

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

// fakeWorkloadGraphReader dispatches Cypher queries based on content matching.
type fakeWorkloadGraphReader struct {
	runSingleByMatch map[string]map[string]any
	runByMatch       map[string][]map[string]any
}

func (f fakeWorkloadGraphReader) Run(_ context.Context, cypher string, _ map[string]any) ([]map[string]any, error) {
	for fragment, rows := range f.runByMatch {
		if strings.Contains(cypher, fragment) {
			return rows, nil
		}
	}
	return nil, nil
}

func (f fakeWorkloadGraphReader) RunSingle(_ context.Context, cypher string, _ map[string]any) (map[string]any, error) {
	for fragment, row := range f.runSingleByMatch {
		if strings.Contains(cypher, fragment) {
			return row, nil
		}
	}
	return nil, nil
}

func TestGetWorkloadContextReturnsEnrichedResponse(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				// Base workload query
				"MATCH (w:Workload)": {
					"id":        "workload-1",
					"name":      "order-service",
					"kind":      "Deployment",
					"repo_id":   "repo-1",
					"repo_name": "order-service",
					"instances": []any{
						map[string]any{
							"instance_id":   "inst-1",
							"platform_name": "eks-prod",
							"platform_kind": "EKS",
							"environment":   "production",
						},
					},
				},
			},
			runByMatch: map[string][]map[string]any{
				// Dependencies query
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {
					{
						"type":          "DEPENDS_ON",
						"target_name":   "auth-service",
						"target_id":     "repo-2",
						"evidence_type": "terraform_module_source",
					},
				},
				// Infrastructure query
				"K8sResource OR": {
					{
						"type":      "K8sResource",
						"name":      "order-deployment",
						"kind":      "Deployment",
						"file_path": "k8s/deployment.yaml",
					},
				},
				// Entry points query
				"fn.name IN": {
					{
						"name":          "main",
						"relative_path": "cmd/server/main.go",
						"language":      "go",
					},
				},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/workloads/workload-1/context", nil)
	req.SetPathValue("workload_id", "workload-1")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	// Base workload fields present
	if got, want := resp["id"], "workload-1"; got != want {
		t.Fatalf("id = %v, want %v", got, want)
	}
	if got, want := resp["name"], "order-service"; got != want {
		t.Fatalf("name = %v, want %v", got, want)
	}
	if got, want := resp["repo_id"], "repo-1"; got != want {
		t.Fatalf("repo_id = %v, want %v", got, want)
	}

	// Instances present
	instances, ok := resp["instances"].([]any)
	if !ok {
		t.Fatalf("instances type = %T, want []any", resp["instances"])
	}
	if len(instances) != 1 {
		t.Fatalf("len(instances) = %d, want 1", len(instances))
	}

	// Dependencies from repo enrichment
	deps, ok := resp["dependencies"].([]any)
	if !ok {
		t.Fatalf("dependencies type = %T, want []any", resp["dependencies"])
	}
	if len(deps) != 1 {
		t.Fatalf("len(dependencies) = %d, want 1", len(deps))
	}
	dep0, ok := deps[0].(map[string]any)
	if !ok {
		t.Fatalf("dependencies[0] type = %T", deps[0])
	}
	if got, want := dep0["type"], "DEPENDS_ON"; got != want {
		t.Fatalf("dependencies[0].type = %v, want %v", got, want)
	}

	// Infrastructure from repo enrichment
	infra, ok := resp["infrastructure"].([]any)
	if !ok {
		t.Fatalf("infrastructure type = %T, want []any", resp["infrastructure"])
	}
	if len(infra) != 1 {
		t.Fatalf("len(infrastructure) = %d, want 1", len(infra))
	}

	if _, exists := resp["entry_points"]; exists {
		t.Fatalf("entry_points = %#v, want omitted for workload context", resp["entry_points"])
	}
}

func TestGetWorkloadContextReturnsNotFoundForMissingWorkload(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{},
			runByMatch:       map[string][]map[string]any{},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/workloads/unknown/context", nil)
	req.SetPathValue("workload_id", "unknown")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusNotFound; got != want {
		t.Fatalf("status = %d, want %d", got, want)
	}
}

func TestGetWorkloadContextSkipsEnrichmentWhenNoRepoID(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"MATCH (w:Workload)": {
					"id":        "workload-orphan",
					"name":      "orphan-service",
					"kind":      "Deployment",
					"repo_id":   "",
					"repo_name": "",
					"instances": []any{},
				},
			},
			runByMatch: map[string][]map[string]any{},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/workloads/workload-orphan/context", nil)
	req.SetPathValue("workload_id", "workload-orphan")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	// No enrichment sections when repo_id is empty
	if _, exists := resp["dependencies"]; exists {
		t.Fatal("dependencies should not be present when repo_id is empty")
	}
	if _, exists := resp["infrastructure"]; exists {
		t.Fatal("infrastructure should not be present when repo_id is empty")
	}
	if _, exists := resp["entry_points"]; exists {
		t.Fatal("entry_points should not be present when repo_id is empty")
	}
}

func TestGetServiceContextAcceptsQualifiedWorkloadID(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"w.name = $service_name OR w.id = $service_name": {
					"id":        "workload:service-edge-api",
					"name":      "service-edge-api",
					"kind":      "Deployment",
					"repo_id":   "repo-1",
					"repo_name": "service-edge-api",
					"instances": []any{
						map[string]any{
							"instance_id":   "inst-1",
							"platform_name": "eks-prod",
							"platform_kind": "EKS",
							"environment":   "production",
						},
					},
				},
			},
			runByMatch: map[string][]map[string]any{
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {},
				"K8sResource OR":                      {},
				"fn.name IN":                          {},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/services/workload:service-edge-api/context", nil)
	req.SetPathValue("service_name", "workload:service-edge-api")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if got, want := resp["id"], "workload:service-edge-api"; got != want {
		t.Fatalf("id = %v, want %v", got, want)
	}
	if got, want := resp["name"], "service-edge-api"; got != want {
		t.Fatalf("name = %v, want %v", got, want)
	}
}

func TestGetServiceStoryAcceptsPlainServiceName(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"w.name = $service_name OR w.id = $service_name": {
					"id":        "workload:service-edge-api",
					"name":      "service-edge-api",
					"kind":      "Deployment",
					"repo_id":   "repo-1",
					"repo_name": "service-edge-api",
					"instances": []any{
						map[string]any{
							"instance_id":   "inst-1",
							"platform_name": "eks-prod",
							"platform_kind": "EKS",
							"environment":   "production",
						},
					},
				},
			},
			runByMatch: map[string][]map[string]any{
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {},
				"K8sResource OR":                      {},
				"fn.name IN":                          {},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/services/service-edge-api/story", nil)
	req.SetPathValue("service_name", "service-edge-api")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if got, want := resp["service_name"], "service-edge-api"; got != want {
		t.Fatalf("service_name = %v, want %v", got, want)
	}
	if got, ok := resp["story"].(string); !ok || !strings.Contains(got, "Workload service-edge-api") {
		t.Fatalf("story = %#v, want narrative for service-edge-api", resp["story"])
	}
}

func TestGetServiceStoryAcceptsQualifiedWorkloadIDAndNormalizesServiceName(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"w.name = $service_name OR w.id = $service_name": {
					"id":        "workload:service-edge-api",
					"name":      "service-edge-api",
					"kind":      "Deployment",
					"repo_id":   "repo-1",
					"repo_name": "service-edge-api",
					"instances": []any{
						map[string]any{
							"instance_id":   "inst-1",
							"platform_name": "eks-prod",
							"platform_kind": "EKS",
							"environment":   "production",
						},
					},
				},
			},
			runByMatch: map[string][]map[string]any{
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {},
				"K8sResource OR":                      {},
				"fn.name IN":                          {},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/services/workload:service-edge-api/story", nil)
	req.SetPathValue("service_name", "workload:service-edge-api")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if got, want := resp["service_name"], "service-edge-api"; got != want {
		t.Fatalf("service_name = %v, want %v", got, want)
	}
	if got, ok := resp["story"].(string); !ok || !strings.Contains(got, "Workload service-edge-api") {
		t.Fatalf("story = %#v, want narrative for service-edge-api", resp["story"])
	}
}

func TestGetServiceContextOmitsRepoEntryPoints(t *testing.T) {
	t.Parallel()

	handler := &EntityHandler{
		Neo4j: fakeWorkloadGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"w.name = $service_name OR w.id = $service_name": {
					"id":        "workload:service-edge-api",
					"name":      "service-edge-api",
					"kind":      "Deployment",
					"repo_id":   "repo-1",
					"repo_name": "service-edge-api",
					"instances": []any{
						map[string]any{
							"instance_id":   "inst-1",
							"platform_name": "eks-prod",
							"platform_kind": "EKS",
							"environment":   "production",
						},
					},
				},
			},
			runByMatch: map[string][]map[string]any{
				"DEPENDS_ON|USES_MODULE|DEPLOYS_FROM": {},
				"K8sResource OR":                      {},
				"fn.name IN": {
					{
						"name":          "main",
						"relative_path": "cmd/server/main.go",
						"language":      "go",
					},
				},
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(http.MethodGet, "/api/v0/services/service-edge-api/context", nil)
	req.SetPathValue("service_name", "service-edge-api")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	if _, exists := resp["entry_points"]; exists {
		t.Fatalf("entry_points = %#v, want omitted for service context", resp["entry_points"])
	}
}

func TestBuildWorkloadStorySurfacesObservedServiceSignalsWithoutMaterializedInstances(t *testing.T) {
	t.Parallel()

	ctx := map[string]any{
		"name":      "sample-service-api",
		"kind":      "service",
		"repo_name": "sample-service-api",
		"instances": []map[string]any{},
		"observed_config_environments": []string{
			"production",
			"qa",
		},
		"hostnames": []map[string]any{
			{"hostname": "sample-service-api.qa.example.com"},
			{"hostname": "sample-service-api.production.example.com"},
		},
		"api_surface": map[string]any{
			"endpoint_count": 21,
			"spec_count":     1,
			"docs_routes":    []string{"/_specs"},
		},
	}

	story := buildWorkloadStory(ctx)
	for _, fragment := range []string{
		"No materialized workload instances found.",
		"Observed config environments: production, qa.",
		"Public entrypoints: sample-service-api.production.example.com, sample-service-api.qa.example.com.",
		"API surface exposes 21 endpoint(s) across 1 spec file(s).",
		"Docs routes: /_specs.",
	} {
		if !strings.Contains(story, fragment) {
			t.Fatalf("story = %q, want fragment %q", story, fragment)
		}
	}
}
