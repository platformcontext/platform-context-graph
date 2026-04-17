package query

import "testing"

func TestBuildSharedConfigPathsGroupsDuplicatePathsAcrossRepos(t *testing.T) {
	t.Parallel()

	got := buildSharedConfigPaths(map[string]any{
		"config_paths": []map[string]any{
			{
				"path":          "/configd/payments/*",
				"source_repo":   "helm-charts",
				"relative_path": "deploy/policy.yaml",
				"evidence_kind": "kustomize_policy_document_resource",
			},
			{
				"path":          "/configd/payments/*",
				"source_repo":   "terraform-stack-payments",
				"relative_path": "env/prod/terragrunt.hcl",
				"evidence_kind": "terragrunt_dependency_config_path",
			},
			{
				"path":          "/configd/payments/*",
				"source_repo":   "helm-charts",
				"relative_path": "deploy/policy.yaml",
				"evidence_kind": "kustomize_policy_document_resource",
			},
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

	evidenceKinds, ok := got[0]["evidence_kinds"].([]string)
	if !ok {
		t.Fatalf("evidence_kinds type = %T, want []string", got[0]["evidence_kinds"])
	}
	if len(evidenceKinds) != 2 {
		t.Fatalf("len(evidence_kinds) = %d, want 2", len(evidenceKinds))
	}
	if evidenceKinds[0] != "kustomize_policy_document_resource" || evidenceKinds[1] != "terragrunt_dependency_config_path" {
		t.Fatalf("evidence_kinds = %#v, want sorted unique evidence kinds", evidenceKinds)
	}

	relativePaths, ok := got[0]["relative_paths"].([]string)
	if !ok {
		t.Fatalf("relative_paths type = %T, want []string", got[0]["relative_paths"])
	}
	if len(relativePaths) != 2 {
		t.Fatalf("len(relative_paths) = %d, want 2", len(relativePaths))
	}
	if relativePaths[0] != "deploy/policy.yaml" || relativePaths[1] != "env/prod/terragrunt.hcl" {
		t.Fatalf("relative_paths = %#v, want sorted unique relative paths", relativePaths)
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
						"ansible_inventories": []string{
							"inventory/dynamic_hosts.py",
						},
						"ansible_var_files": []string{
							"group_vars/all.yml",
							"host_vars/web-prod.yml",
						},
						"ansible_task_entrypoints": []string{
							"roles/website_import/tasks/main.yml",
						},
						"ansible_playbook_hints": []map[string]any{
							{"playbook": "deploy.yml"},
						},
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
	if got, want := topologyStory[0], "Controller delivery paths include Jenkinsfile via jenkins_pipeline (entry points dist/api.js; shared libraries pipelines; ansible playbooks deploy.yml; ansible inventories inventory/dynamic_hosts.py; ansible vars group_vars/all.yml, host_vars/web-prod.yml; ansible task entrypoints roles/website_import/tasks/main.yml)."; got != want {
		t.Fatalf("topology_story[0] = %q, want %q", got, want)
	}
	if got, want := topologyStory[1], "Runtime artifacts include docker_compose service api in docker-compose.yaml built from ./ (build, ports)."; got != want {
		t.Fatalf("topology_story[1] = %q, want %q", got, want)
	}
}

func TestBuildRepositoryDeploymentOverviewIncludesDockerfileRuntimeStory(t *testing.T) {
	t.Parallel()

	got := BuildRepositoryDeploymentOverview(
		[]string{"payments-api"},
		[]string{"ecs_service"},
		[]string{"docker"},
		map[string]any{
			"deployment_artifacts": map[string]any{
				"deployment_artifacts": []map[string]any{
					{
						"relative_path": "Dockerfile",
						"artifact_type": "dockerfile",
						"artifact_name": "runtime",
						"base_image":    "alpine",
						"cmd":           `["/app", "--serve"]`,
						"signals":       []string{"base_image", "copy_from", "cmd", "ports"},
					},
				},
			},
		},
	)

	deliveryPaths, ok := got["delivery_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_paths type = %T, want []map[string]any", got["delivery_paths"])
	}
	if len(deliveryPaths) != 1 {
		t.Fatalf("len(delivery_paths) = %d, want 1", len(deliveryPaths))
	}
	if got, want := deliveryPaths[0]["artifact_name"], "runtime"; got != want {
		t.Fatalf("delivery_paths[0].artifact_name = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["cmd"], `["/app", "--serve"]`; got != want {
		t.Fatalf("delivery_paths[0].cmd = %#v, want %#v", got, want)
	}

	topologyStory, ok := got["topology_story"].([]string)
	if !ok {
		t.Fatalf("topology_story type = %T, want []string", got["topology_story"])
	}
	if len(topologyStory) != 1 {
		t.Fatalf("len(topology_story) = %d, want 1", len(topologyStory))
	}
	if got, want := topologyStory[0], "Runtime artifacts include dockerfile stage runtime in Dockerfile based on alpine with cmd [\"/app\", \"--serve\"] (base_image, copy_from, cmd, ports)."; got != want {
		t.Fatalf("topology_story[0] = %q, want %q", got, want)
	}
}

func TestBuildRepositoryDeploymentOverviewIncludesWorkflowArtifactsInDeliveryPaths(t *testing.T) {
	t.Parallel()

	got := BuildRepositoryDeploymentOverview(
		[]string{"payments-api"},
		[]string{"argocd_application"},
		[]string{"github_actions"},
		map[string]any{
			"deployment_artifacts": map[string]any{
				"workflow_artifacts": []map[string]any{
					{
						"relative_path": ".github/workflows/deploy.yaml",
						"artifact_type": "github_actions_workflow",
						"workflow_name": "deploy",
						"signals":       []string{"workflow_file"},
					},
				},
			},
		},
	)

	deliveryPaths, ok := got["delivery_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_paths type = %T, want []map[string]any", got["delivery_paths"])
	}
	if len(deliveryPaths) != 1 {
		t.Fatalf("len(delivery_paths) = %d, want 1", len(deliveryPaths))
	}
	if got, want := deliveryPaths[0]["kind"], "workflow_artifact"; got != want {
		t.Fatalf("delivery_paths[0].kind = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["workflow_name"], "deploy"; got != want {
		t.Fatalf("delivery_paths[0].workflow_name = %#v, want %#v", got, want)
	}

	topologyStory, ok := got["topology_story"].([]string)
	if !ok {
		t.Fatalf("topology_story type = %T, want []string", got["topology_story"])
	}
	if len(topologyStory) != 1 {
		t.Fatalf("len(topology_story) = %d, want 1", len(topologyStory))
	}
	if got, want := topologyStory[0], "Workflow delivery paths include .github/workflows/deploy.yaml as github_actions_workflow deploy (workflow_file)."; got != want {
		t.Fatalf("topology_story[0] = %q, want %q", got, want)
	}
}

func TestBuildRepositoryDeploymentOverviewIncludesSingleSourceConfigPathsInDeliveryPaths(t *testing.T) {
	t.Parallel()

	got := BuildRepositoryDeploymentOverview(
		[]string{"payments-api"},
		[]string{"argocd_application"},
		[]string{"terraform", "terragrunt"},
		map[string]any{
			"deployment_artifacts": map[string]any{
				"config_paths": []map[string]any{
					{
						"path":          "root.hcl",
						"source_repo":   "terraform-stack-payments",
						"relative_path": "env/prod/terragrunt.hcl",
						"evidence_kind": "terragrunt_include_path",
					},
				},
			},
		},
	)

	deliveryPaths, ok := got["delivery_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("delivery_paths type = %T, want []map[string]any", got["delivery_paths"])
	}
	if len(deliveryPaths) != 1 {
		t.Fatalf("len(delivery_paths) = %d, want 1", len(deliveryPaths))
	}
	if got, want := deliveryPaths[0]["kind"], "config_artifact"; got != want {
		t.Fatalf("delivery_paths[0].kind = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["path"], "root.hcl"; got != want {
		t.Fatalf("delivery_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["source_repo"], "terraform-stack-payments"; got != want {
		t.Fatalf("delivery_paths[0].source_repo = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["relative_path"], "env/prod/terragrunt.hcl"; got != want {
		t.Fatalf("delivery_paths[0].relative_path = %#v, want %#v", got, want)
	}
	if got, want := deliveryPaths[0]["evidence_kind"], "terragrunt_include_path"; got != want {
		t.Fatalf("delivery_paths[0].evidence_kind = %#v, want %#v", got, want)
	}

	topologyStory, ok := got["topology_story"].([]string)
	if !ok {
		t.Fatalf("topology_story type = %T, want []string", got["topology_story"])
	}
	if len(topologyStory) != 1 {
		t.Fatalf("len(topology_story) = %d, want 1", len(topologyStory))
	}
	if got, want := topologyStory[0], "Config provenance includes root.hcl from terraform-stack-payments via terragrunt_include_path in env/prod/terragrunt.hcl."; got != want {
		t.Fatalf("topology_story[0] = %q, want %q", got, want)
	}
}
