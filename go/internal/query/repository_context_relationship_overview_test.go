package query

import (
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
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
					"dependency_count": int64(5),
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
					{
						"type":          "DISCOVERS_CONFIG_IN",
						"target_name":   "shared-pipelines",
						"target_id":     "repo-5",
						"evidence_type": "jenkins_shared_library",
					},
					{
						"type":          "DEPENDS_ON",
						"target_name":   "ansible-ops",
						"target_id":     "repo-6",
						"evidence_type": "ansible_role_reference",
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

	if got, want := resp["workload_count"], float64(1); got != want {
		t.Fatalf("workload_count = %#v, want %#v", got, want)
	}
	if got, want := resp["platform_count"], float64(1); got != want {
		t.Fatalf("platform_count = %#v, want %#v", got, want)
	}

	overview, ok := resp["relationship_overview"].(map[string]any)
	if !ok {
		t.Fatalf("relationship_overview type = %T, want map[string]any", resp["relationship_overview"])
	}

	if got, want := overview["relationship_count"], float64(5); got != want {
		t.Fatalf("relationship_overview.relationship_count = %#v, want %#v", got, want)
	}

	controllerDriven, ok := overview["controller_driven"].([]any)
	if !ok {
		t.Fatalf("controller_driven type = %T, want []any", overview["controller_driven"])
	}
	if len(controllerDriven) != 3 {
		t.Fatalf("len(controller_driven) = %d, want 3", len(controllerDriven))
	}
	controllerEvidence := map[string]struct{}{}
	for index, item := range controllerDriven {
		row, ok := item.(map[string]any)
		if !ok {
			t.Fatalf("controller_driven[%d] type = %T, want map[string]any", index, item)
		}
		controllerEvidence[StringVal(row, "evidence_type")] = struct{}{}
	}
	for _, want := range []string{"argocd_application_source", "ansible_role_reference", "jenkins_shared_library"} {
		if _, ok := controllerEvidence[want]; !ok {
			t.Fatalf("controller_driven missing evidence_type %q", want)
		}
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

	iacDriven, ok := overview["iac_driven"].([]any)
	if !ok {
		t.Fatalf("iac_driven type = %T, want []any", overview["iac_driven"])
	}
	if len(iacDriven) != 1 {
		t.Fatalf("len(iac_driven) = %d, want 1", len(iacDriven))
	}
	iacRow, ok := iacDriven[0].(map[string]any)
	if !ok {
		t.Fatalf("iac_driven[0] type = %T, want map[string]any", iacDriven[0])
	}
	if got, want := iacRow["evidence_type"], "terraform_module_source"; got != want {
		t.Fatalf("iac_driven[0].evidence_type = %#v, want %#v", got, want)
	}

	relationshipTypes, ok := overview["relationship_types"].([]any)
	if !ok {
		t.Fatalf("relationship_types type = %T, want []any", overview["relationship_types"])
	}
	if len(relationshipTypes) != 3 {
		t.Fatalf("len(relationship_types) = %d, want 3", len(relationshipTypes))
	}
	for _, want := range []string{"DEPENDS_ON", "DEPLOYS_FROM", "DISCOVERS_CONFIG_IN"} {
		if !containsStringAny(relationshipTypes, want) {
			t.Fatalf("relationship_types missing %q", want)
		}
	}
	for _, runtimeEdge := range []string{"PROVISIONS_PLATFORM", "DEFINES", "INSTANCE_OF"} {
		if containsStringAny(relationshipTypes, runtimeEdge) {
			t.Fatalf("relationship_types unexpectedly includes runtime edge %q", runtimeEdge)
		}
	}

	if otherRelationships, ok := overview["other_relationships"].([]any); ok && len(otherRelationships) != 0 {
		t.Fatalf("len(other_relationships) = %d, want 0 after family partitioning", len(otherRelationships))
	}

	story, ok := overview["story"].(string)
	if !ok {
		t.Fatalf("story type = %T, want string", overview["story"])
	}
	if !strings.Contains(strings.ToLower(story), "iac-driven") {
		t.Fatalf("story = %q, want IaC-driven relationship narrative", story)
	}
}

func containsStringAny(values []any, want string) bool {
	for _, value := range values {
		got, ok := value.(string)
		if ok && got == want {
			return true
		}
	}
	return false
}
