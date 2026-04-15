package query

import "testing"

func TestBuildRepositoryStoryResponseIncludesStructuredOverviews(t *testing.T) {
	t.Parallel()

	repo := RepoRef{
		ID:        "repository:payments",
		Name:      "payments",
		LocalPath: "/workspace/payments",
		RemoteURL: "https://github.com/acme/payments.git",
		RepoSlug:  "acme/payments",
		HasRemote: true,
	}

	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"go", "yaml"},
		[]string{"payments-api"},
		[]string{"argocd_application"},
		3,
	)

	subject, ok := got["subject"].(map[string]any)
	if !ok {
		t.Fatalf("subject type = %T, want map[string]any", got["subject"])
	}
	if subject["name"] != "payments" {
		t.Fatalf("subject.name = %#v, want %q", subject["name"], "payments")
	}

	if got["story"] == "" {
		t.Fatal("story is empty, want narrative summary")
	}

	storySections, ok := got["story_sections"].([]map[string]any)
	if !ok {
		t.Fatalf("story_sections type = %T, want []map[string]any", got["story_sections"])
	}
	if len(storySections) == 0 {
		t.Fatal("story_sections is empty, want grouped context")
	}

	deploymentOverview, ok := got["deployment_overview"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_overview type = %T, want map[string]any", got["deployment_overview"])
	}
	if deploymentOverview["workload_count"] != 1 {
		t.Fatalf("deployment_overview.workload_count = %#v, want 1", deploymentOverview["workload_count"])
	}
	if deploymentOverview["platform_count"] != 1 {
		t.Fatalf("deployment_overview.platform_count = %#v, want 1", deploymentOverview["platform_count"])
	}

	gitopsOverview, ok := got["gitops_overview"].(map[string]any)
	if !ok {
		t.Fatalf("gitops_overview type = %T, want map[string]any", got["gitops_overview"])
	}
	if gitopsOverview["enabled"] != true {
		t.Fatalf("gitops_overview.enabled = %#v, want true", gitopsOverview["enabled"])
	}

	documentationOverview, ok := got["documentation_overview"].(map[string]any)
	if !ok {
		t.Fatalf("documentation_overview type = %T, want map[string]any", got["documentation_overview"])
	}
	if documentationOverview["repo_slug"] != "acme/payments" {
		t.Fatalf("documentation_overview.repo_slug = %#v, want %q", documentationOverview["repo_slug"], "acme/payments")
	}

	supportOverview, ok := got["support_overview"].(map[string]any)
	if !ok {
		t.Fatalf("support_overview type = %T, want map[string]any", got["support_overview"])
	}
	if supportOverview["dependency_count"] != 3 {
		t.Fatalf("support_overview.dependency_count = %#v, want 3", supportOverview["dependency_count"])
	}

	coverageSummary, ok := got["coverage_summary"].(map[string]any)
	if !ok {
		t.Fatalf("coverage_summary type = %T, want map[string]any", got["coverage_summary"])
	}
	if coverageSummary["status"] != "unknown" {
		t.Fatalf("coverage_summary.status = %#v, want %q", coverageSummary["status"], "unknown")
	}

	limitations, ok := got["limitations"].([]string)
	if !ok {
		t.Fatalf("limitations type = %T, want []string", got["limitations"])
	}
	if len(limitations) == 0 {
		t.Fatal("limitations is empty, want truthful limitation note")
	}

	drilldowns, ok := got["drilldowns"].(map[string]any)
	if !ok {
		t.Fatalf("drilldowns type = %T, want map[string]any", got["drilldowns"])
	}
	if drilldowns["context_path"] != "/api/v0/repositories/repository:payments/context" {
		t.Fatalf("drilldowns.context_path = %#v", drilldowns["context_path"])
	}
}
