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

type recordingInfraGraphReader struct {
	runRows    []map[string]any
	lastCypher string
	lastParams map[string]any
}

func (r *recordingInfraGraphReader) Run(_ context.Context, cypher string, params map[string]any) ([]map[string]any, error) {
	r.lastCypher = cypher
	r.lastParams = params
	return r.runRows, nil
}

func (*recordingInfraGraphReader) RunSingle(context.Context, string, map[string]any) (map[string]any, error) {
	return nil, nil
}

func TestSearchInfraResourcesUsesInfrastructureLabelsForCategory(t *testing.T) {
	t.Parallel()

	reader := &recordingInfraGraphReader{
		runRows: []map[string]any{
			{
				"id":          "k8s:configmap:boats",
				"name":        "api-node-boats",
				"labels":      []any{"K8sResource"},
				"kind":        "ConfigMap",
				"provider":    "kubernetes",
				"environment": "qa",
				"source":      "deploy/qa/configmap.yaml",
				"config_path": "",
			},
		},
	}
	handler := &InfraHandler{Neo4j: reader}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/infra/resources/search",
		bytes.NewBufferString(`{"query":"api-node-boats","category":"k8s","limit":5}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}
	if strings.Contains(reader.lastCypher, "Platform") || strings.Contains(reader.lastCypher, "Workload") {
		t.Fatalf("cypher = %q, want infrastructure-only label search", reader.lastCypher)
	}

	labels, ok := reader.lastParams["labels"].([]string)
	if !ok {
		t.Fatalf("params[labels] type = %T, want []string", reader.lastParams["labels"])
	}
	if got, want := len(labels), 2; got != want {
		t.Fatalf("len(params[labels]) = %d, want %d", got, want)
	}
	if got, want := labels[0], "K8sResource"; got != want {
		t.Fatalf("labels[0] = %q, want %q", got, want)
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if got, want := int(resp["count"].(float64)), 1; got != want {
		t.Fatalf("count = %d, want %d", got, want)
	}
}

func TestSearchInfraResourcesRejectsUnknownCategory(t *testing.T) {
	t.Parallel()

	handler := &InfraHandler{Neo4j: &recordingInfraGraphReader{}}

	mux := http.NewServeMux()
	handler.Mount(mux)

	req := httptest.NewRequest(
		http.MethodPost,
		"/api/v0/infra/resources/search",
		bytes.NewBufferString(`{"query":"api-node-boats","category":"unknown"}`),
	)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusBadRequest; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}
	if got, want := resp["detail"], "unsupported category"; got != want {
		t.Fatalf("detail = %#v, want %#v", got, want)
	}
}
