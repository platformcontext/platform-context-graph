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
		4,
		map[string]any{
			"families": []string{"argocd", "helm", "terraform"},
		},
		nil,
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
	if got, ok := deploymentOverview["infrastructure_families"].([]string); !ok || len(got) != 3 {
		t.Fatalf("deployment_overview.infrastructure_families = %#v, want 3 families", deploymentOverview["infrastructure_families"])
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
	if supportOverview["dependency_count"] != 4 {
		t.Fatalf("support_overview.dependency_count = %#v, want 4", supportOverview["dependency_count"])
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

func TestBuildRepositoryStoryResponseOmitsSharedConfigFromDirectStory(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:payments", Name: "payments"}
	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"go"},
		[]string{"payments-api"},
		[]string{"argocd_application"},
		2,
		map[string]any{
			"families": []string{"terraform"},
			"deployment_artifacts": map[string]any{
				"config_paths": []map[string]any{
					{"path": "/configd/payments/*", "source_repo": "helm-charts"},
					{"path": "/configd/payments/*", "source_repo": "terraform-stack-payments"},
				},
			},
		},
		nil,
	)

	deploymentOverview, ok := got["deployment_overview"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_overview type = %T, want map[string]any", got["deployment_overview"])
	}
	topologyStory, ok := deploymentOverview["topology_story"].([]string)
	if !ok || len(topologyStory) != 1 {
		t.Fatalf("topology_story = %#v, want one shared-config line", deploymentOverview["topology_story"])
	}
	if got, want := topologyStory[0], "Shared config families span /configd/payments/* across helm-charts, terraform-stack-payments."; got != want {
		t.Fatalf("topology_story[0] = %q, want %q", got, want)
	}
	directStory, ok := deploymentOverview["direct_story"].([]string)
	if !ok {
		t.Fatalf("direct_story type = %T, want []string", deploymentOverview["direct_story"])
	}
	if len(directStory) != 0 {
		t.Fatalf("direct_story = %#v, want shared-config line omitted", directStory)
	}
	traceLimitations, ok := deploymentOverview["trace_limitations"].(map[string]any)
	if !ok {
		t.Fatalf("trace_limitations type = %T, want map[string]any", deploymentOverview["trace_limitations"])
	}
	omittedSections, ok := traceLimitations["omitted_sections"].([]string)
	if !ok {
		t.Fatalf("omitted_sections type = %T, want []string", traceLimitations["omitted_sections"])
	}
	if len(omittedSections) != 1 || omittedSections[0] != "shared_config_paths" {
		t.Fatalf("omitted_sections = %#v, want [shared_config_paths]", omittedSections)
	}
}

func TestBuildRepositoryStoryResponsePreservesDeliveryPathsInDirectStory(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:payments", Name: "payments"}
	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"go"},
		[]string{"payments-api"},
		[]string{"argocd_application"},
		2,
		map[string]any{
			"families": []string{"terraform"},
			"deployment_artifacts": map[string]any{
				"controller_artifacts": []map[string]any{
					{
						"path":            "Jenkinsfile",
						"controller_kind": "jenkins_pipeline",
						"entry_points":    []string{"dist/api.js"},
					},
				},
				"deployment_artifacts": []map[string]any{
					{
						"relative_path": "docker-compose.yaml",
						"artifact_type": "docker_compose",
						"service_name":  "api",
						"signals":       []string{"build", "ports"},
					},
				},
				"config_paths": []map[string]any{
					{"path": "/configd/payments/*", "source_repo": "helm-charts"},
					{"path": "/configd/payments/*", "source_repo": "terraform-stack-payments"},
					{
						"path":          "root.hcl",
						"source_repo":   "terraform-stack-payments",
						"relative_path": "env/prod/terragrunt.hcl",
						"evidence_kind": "terragrunt_include_path",
					},
				},
			},
		},
		nil,
	)

	deploymentOverview, ok := got["deployment_overview"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_overview type = %T, want map[string]any", got["deployment_overview"])
	}
	directStory, ok := deploymentOverview["direct_story"].([]string)
	if !ok {
		t.Fatalf("direct_story type = %T, want []string", deploymentOverview["direct_story"])
	}
	if len(directStory) != 3 {
		t.Fatalf("len(direct_story) = %d, want 3", len(directStory))
	}
	if got, want := directStory[0], "Controller delivery paths include Jenkinsfile via jenkins_pipeline."; got != want {
		t.Fatalf("direct_story[0] = %q, want %q", got, want)
	}
	if got, want := directStory[1], "Runtime artifacts include docker_compose service api in docker-compose.yaml (build, ports)."; got != want {
		t.Fatalf("direct_story[1] = %q, want %q", got, want)
	}
	if got, want := directStory[2], "Config provenance includes root.hcl from terraform-stack-payments via terragrunt_include_path in env/prod/terragrunt.hcl."; got != want {
		t.Fatalf("direct_story[2] = %q, want %q", got, want)
	}
}
