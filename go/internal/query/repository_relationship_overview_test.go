package query

import "testing"

func TestBuildRepositoryRelationshipOverviewSeparatesControllerAndWorkflowEvidence(t *testing.T) {
	t.Parallel()

	overview := buildRepositoryRelationshipOverview([]map[string]any{
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
	})

	if overview == nil {
		t.Fatal("buildRepositoryRelationshipOverview() = nil, want typed relationship overview")
	}

	if got, want := overview["relationship_count"], 3; got != want {
		t.Fatalf("relationship_count = %#v, want %#v", got, want)
	}

	evidenceTypes, ok := overview["evidence_types"].([]string)
	if !ok {
		t.Fatalf("evidence_types type = %T, want []string", overview["evidence_types"])
	}
	if len(evidenceTypes) != 3 {
		t.Fatalf("len(evidence_types) = %d, want 3", len(evidenceTypes))
	}

	controllerDriven, ok := overview["controller_driven"].([]map[string]any)
	if !ok {
		t.Fatalf("controller_driven type = %T, want []map[string]any", overview["controller_driven"])
	}
	if len(controllerDriven) != 1 {
		t.Fatalf("len(controller_driven) = %d, want 1", len(controllerDriven))
	}
	if got, want := controllerDriven[0]["evidence_type"], "argocd_application_source"; got != want {
		t.Fatalf("controller_driven[0].evidence_type = %#v, want %#v", got, want)
	}

	workflowDriven, ok := overview["workflow_driven"].([]map[string]any)
	if !ok {
		t.Fatalf("workflow_driven type = %T, want []map[string]any", overview["workflow_driven"])
	}
	if len(workflowDriven) != 1 {
		t.Fatalf("len(workflow_driven) = %d, want 1", len(workflowDriven))
	}
	if got, want := workflowDriven[0]["evidence_type"], "github_actions_reusable_workflow_ref"; got != want {
		t.Fatalf("workflow_driven[0].evidence_type = %#v, want %#v", got, want)
	}

	story, ok := overview["story"].(string)
	if !ok {
		t.Fatalf("story type = %T, want string", overview["story"])
	}
	if story == "" {
		t.Fatal("story is empty, want typed relationship narrative")
	}
}
