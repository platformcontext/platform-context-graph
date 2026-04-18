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

type fakeCompareGraphReader struct {
	workloadRow map[string]any
}

func (f fakeCompareGraphReader) RunSingle(_ context.Context, cypher string, _ map[string]any) (map[string]any, error) {
	switch {
	case strings.Contains(cypher, "MATCH (w:Workload)"):
		return f.workloadRow, nil
	case strings.Contains(cypher, "MATCH (i:WorkloadInstance)"):
		return nil, nil
	default:
		return nil, nil
	}
}

func (fakeCompareGraphReader) Run(context.Context, string, map[string]any) ([]map[string]any, error) {
	return nil, nil
}

func TestCompareEnvironmentsReturnsExplicitUnsupportedWhenInstancesAreNotMaterialized(t *testing.T) {
	t.Parallel()

	handler := &CompareHandler{
		Neo4j: fakeCompareGraphReader{
			workloadRow: map[string]any{
				"id":      "workload:api-node-boats",
				"name":    "api-node-boats",
				"kind":    "service",
				"repo_id": "repository:r_472ddee5",
			},
		},
	}

	mux := http.NewServeMux()
	handler.Mount(mux)

	body := bytes.NewBufferString(`{"workload_id":"workload:api-node-boats","left":"qa","right":"prod"}`)
	req := httptest.NewRequest(http.MethodPost, "/api/v0/compare/environments", body)
	req.Header.Set("Content-Type", "application/json")
	w := httptest.NewRecorder()
	mux.ServeHTTP(w, req)

	if got, want := w.Code, http.StatusOK; got != want {
		t.Fatalf("status = %d, want %d; body = %s", got, want, w.Body.String())
	}

	var resp map[string]any
	if err := json.Unmarshal(w.Body.Bytes(), &resp); err != nil {
		t.Fatalf("json.Unmarshal: %v", err)
	}

	left, ok := resp["left"].(map[string]any)
	if !ok {
		t.Fatalf("resp[left] type = %T, want map[string]any", resp["left"])
	}
	if got, want := left["status"], "unsupported"; got != want {
		t.Fatalf("left.status = %#v, want %#v", got, want)
	}
	if got, want := left["reason"], "no materialized workload instance found for environment"; got != want {
		t.Fatalf("left.reason = %#v, want %#v", got, want)
	}

	right, ok := resp["right"].(map[string]any)
	if !ok {
		t.Fatalf("resp[right] type = %T, want map[string]any", resp["right"])
	}
	if got, want := right["status"], "unsupported"; got != want {
		t.Fatalf("right.status = %#v, want %#v", got, want)
	}

	if got, want := resp["confidence"], float64(0); got != want {
		t.Fatalf("confidence = %#v, want %#v", got, want)
	}
	if got, want := resp["reason"], "Comparison unsupported: one or both environments do not have materialized workload instances"; got != want {
		t.Fatalf("reason = %#v, want %#v", got, want)
	}

	changed, ok := resp["changed"].(map[string]any)
	if !ok {
		t.Fatalf("resp[changed] type = %T, want map[string]any", resp["changed"])
	}
	cloudResources, ok := changed["cloud_resources"].([]any)
	if !ok {
		t.Fatalf("changed[cloud_resources] type = %T, want []any", changed["cloud_resources"])
	}
	if len(cloudResources) != 0 {
		t.Fatalf("len(changed[cloud_resources]) = %d, want 0", len(cloudResources))
	}
}
