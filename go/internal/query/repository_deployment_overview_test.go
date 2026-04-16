package query

import "testing"

func TestBuildSharedConfigPathsGroupsDuplicatePathsAcrossRepos(t *testing.T) {
	t.Parallel()

	got := buildSharedConfigPaths(map[string]any{
		"config_paths": []map[string]any{
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
			{"path": "/configd/payments/*", "source_repo": "terraform-stack-payments"},
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
			{"path": "/api/payments/*", "source_repo": "helm-charts"},
		},
	})

	if len(got) != 1 {
		t.Fatalf("len(shared_config_paths) = %d, want 1", len(got))
	}
	if got[0]["path"] != "/configd/payments/*" {
		t.Fatalf("shared_config_paths[0].path = %#v, want %q", got[0]["path"], "/configd/payments/*")
	}
	sourceRepos, ok := got[0]["source_repositories"].([]string)
	if !ok {
		t.Fatalf("source_repositories type = %T, want []string", got[0]["source_repositories"])
	}
	if len(sourceRepos) != 2 {
		t.Fatalf("len(source_repositories) = %d, want 2", len(sourceRepos))
	}
	if sourceRepos[0] != "helm-charts" || sourceRepos[1] != "terraform-stack-payments" {
		t.Fatalf("source_repositories = %#v, want sorted unique repos", sourceRepos)
	}
}

func TestBuildSharedConfigPathsOmitsBlankAndSingleSourceRows(t *testing.T) {
	t.Parallel()

	got := buildSharedConfigPaths(map[string]any{
		"config_paths": []map[string]any{
			{"path": "", "source_repo": "helm-charts"},
			{"path": "/configd/payments/*", "source_repo": ""},
			{"path": "/configd/payments/*", "source_repo": "helm-charts"},
		},
	})

	if len(got) != 0 {
		t.Fatalf("shared_config_paths = %#v, want empty", got)
	}
}

func TestBuildTopologyStoryIncludesSharedConfigLine(t *testing.T) {
	t.Parallel()

	got := buildOverviewTopologyStory(nil, []map[string]any{
		{
			"path":                "/configd/payments/*",
			"source_repositories": []string{"helm-charts", "terraform-stack-payments"},
		},
	})

	if len(got) != 1 {
		t.Fatalf("len(topology_story) = %d, want 1", len(got))
	}
	want := "Shared config families span /configd/payments/* across helm-charts, terraform-stack-payments."
	if got[0] != want {
		t.Fatalf("topology_story[0] = %q, want %q", got[0], want)
	}
}

func TestBuildRepositoryDeploymentOverviewIncludesDeliveryPathsAndWorkflows(t *testing.T) {
	t.Parallel()

	got := BuildRepositoryDeploymentOverview(
		[]string{"payments-api"},
		[]string{"argocd_application"},
		[]string{"argocd", "docker_compose"},
		map[string]any{
			"deployment_artifacts": map[string]any{
				"controller_artifacts": []map[string]any{
					{
						"path":             "Jenkinsfile",
						"controller_kind":  "jenkins_pipeline",
						"shared_libraries": []string{"pipelines"},
						"entry_points":     []string{"dist/api.js"},
					},
				},
				"deployment_artifacts": []map[string]any{
					{
						"relative_path": "docker-compose.yaml",
						"artifact_type": "docker_compose",
						"service_name":  "api",
						"signals":       []string{"build", "ports"},
						"build_context": "./",
					},
				},
			},
		},
	)

	deliveryPaths, ok := got["delivery_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_paths type = %T, want []map[string]any", got["delivery_paths"])
	}
	if len(deliveryPaths) != 2 {
		t.Fatalf("len(delivery_paths) = %d, want 2", len(deliveryPaths))
	}
	if got, want := deliveryPaths[0]["path"], "Jenkinsfile"; got != want {
		t.Fatalf("delivery_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[1]["path"], "docker-compose.yaml"; got != want {
		t.Fatalf("delivery_paths[1].path = %#v, want %#v", got, want)
	}

	deliveryWorkflows, ok := got["delivery_workflows"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_workflows type = %T, want []map[string]any", got["delivery_workflows"])
	}
	if len(deliveryWorkflows) != 1 {
		t.Fatalf("len(delivery_workflows) = %d, want 1", len(deliveryWorkflows))
	}
	if got, want := deliveryWorkflows[0]["controller_kind"], "jenkins_pipeline"; got != want {
		t.Fatalf("delivery_workflows[0].controller_kind = %#v, want %#v", got, want)
	}

	topologyStory, ok := got["topology_story"].([]string)
	if !ok {
		t.Fatalf("topology_story type = %T, want []string", got["topology_story"])
	}
	if len(topologyStory) != 2 {
		t.Fatalf("len(topology_story) = %d, want 2", len(topologyStory))
	}
}
