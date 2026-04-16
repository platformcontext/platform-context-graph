package query

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestGetRepositoryContextIncludesTypedRelationshipOverview(t *testing.T) {
	t.Parallel()

	handler := &RepositoryHandler{
		Neo4j: fakeRepoGraphReader{
			runSingleByMatch: map[string]map[string]any{
				"INSTANCE_OF": {
					"id":               "repo-1",
					"name":             "payments",
					"path":             "/repos/payments",
					"local_path":       "/repos/payments",
					"remote_url":       "https://github.com/acme/payments.git",
					"repo_slug":        "acme/payments",
					"has_remote":       true,
					"file_count":       int64(12),
					"workload_count":   int64(1),
					"platform_count":   int64(1),
					"dependency_count": int64(3),
				},
			},
			runByMatch: map[string][]map[string]any{
				"RETURN type(rel) AS type": {
					{
						"type":          "DEPLOYS_FROM",
						"target_name":   "infra-configs",
						"target_id":     "repo-2",
						"evidence_type": "argocd_application_source",
					},
					{
						"type":          "DEPLOYS_FROM",
						"target_name":   "ci-workflows",
						"target_id":     "repo-3",
						"evidence_type": "github_actions_reusable_workflow_ref",
					},
					{
						"type":          "DEPENDS_ON",
						"target_name":   "terraform-modules",
						"target_id":     "repo-4",
						"evidence_type": "terraform_module_source",
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
		t.Fatalf("json.Unmarshal() error = %v", err)
	}

	overview, ok := resp["relationship_overview"].(map[string]any)
	if !ok {
		t.Fatalf("relationship_overview type = %T, want map[string]any", resp["relationship_overview"])
	}

	if got, want := overview["relationship_count"], float64(3); got != want {
		t.Fatalf("relationship_overview.relationship_count = %#v, want %#v", got, want)
	}

	controllerDriven, ok := overview["controller_driven"].([]any)
	if !ok {
		t.Fatalf("controller_driven type = %T, want []any", overview["controller_driven"])
	}
	if len(controllerDriven) != 1 {
		t.Fatalf("len(controller_driven) = %d, want 1", len(controllerDriven))
	}
	controllerRow, ok := controllerDriven[0].(map[string]any)
	if !ok {
		t.Fatalf("controller_driven[0] type = %T, want map[string]any", controllerDriven[0])
	}
	if got, want := controllerRow["evidence_type"], "argocd_application_source"; got != want {
		t.Fatalf("controller_driven[0].evidence_type = %#v, want %#v", got, want)
	}

	workflowDriven, ok := overview["workflow_driven"].([]any)
	if !ok {
		t.Fatalf("workflow_driven type = %T, want []any", overview["workflow_driven"])
	}
	if len(workflowDriven) != 1 {
		t.Fatalf("len(workflow_driven) = %d, want 1", len(workflowDriven))
	}
	workflowRow, ok := workflowDriven[0].(map[string]any)
	if !ok {
		t.Fatalf("workflow_driven[0] type = %T, want map[string]any", workflowDriven[0])
	}
	if got, want := workflowRow["evidence_type"], "github_actions_reusable_workflow_ref"; got != want {
		t.Fatalf("workflow_driven[0].evidence_type = %#v, want %#v", got, want)
	}
}
