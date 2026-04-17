package query

import "testing"

func TestBuildRepositoryStoryResponsePreservesCombinedDeliverySurfaces(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:platform-service", Name: "platform-service"}
	got := buildRepositoryStoryResponse(
		repo,
		64,
		[]string{"go", "yaml"},
		[]string{"platform-runtime"},
		[]string{"argocd_application", "github_actions"},
		5,
		map[string]any{
			"families": []string{"argocd", "ansible", "github_actions", "docker_compose", "terraform"},
			"deployment_artifacts": map[string]any{
				"controller_artifacts": []map[string]any{
					{
						"path":             "Jenkinsfile",
						"controller_kind":  "jenkins_pipeline",
						"shared_libraries": []string{"pipelines"},
						"pipeline_calls":   []string{"pipelineDeploy"},
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
				"workflow_artifacts": []map[string]any{
					{
						"relative_path": ".github/workflows/deploy.yaml",
						"artifact_type": "github_actions_workflow",
						"workflow_name": "deploy",
						"signals":       []string{"workflow_file"},
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
	if len(directStory) != 4 {
		t.Fatalf("len(direct_story) = %d, want 4", len(directStory))
	}

	want := []string{
		"Workflow delivery paths include .github/workflows/deploy.yaml as github_actions_workflow deploy (workflow_file).",
		"Controller delivery paths include Jenkinsfile via jenkins_pipeline (entry points dist/api.js; shared libraries pipelines; pipeline calls pipelineDeploy; ansible playbooks deploy.yml; ansible inventories inventory/dynamic_hosts.py; ansible vars group_vars/all.yml, host_vars/web-prod.yml; ansible task entrypoints roles/website_import/tasks/main.yml).",
		"Runtime artifacts include docker_compose service api in docker-compose.yaml built from ./ (build, ports).",
		"Config provenance includes root.hcl from terraform-stack-payments via terragrunt_include_path in env/prod/terragrunt.hcl.",
	}
	for i, wantLine := range want {
		if directStory[i] != wantLine {
			t.Fatalf("direct_story[%d] = %q, want %q", i, directStory[i], wantLine)
		}
	}

	topologyStory, ok := deploymentOverview["topology_story"].([]string)
	if !ok {
		t.Fatalf("topology_story type = %T, want []string", deploymentOverview["topology_story"])
	}
	if len(topologyStory) != len(want) {
		t.Fatalf("len(topology_story) = %d, want %d", len(topologyStory), len(want))
	}
	for i, wantLine := range want {
		if topologyStory[i] != wantLine {
			t.Fatalf("topology_story[%d] = %q, want %q", i, topologyStory[i], wantLine)
		}
	}
}

func TestBuildRepositoryStoryResponsePreservesDockerfileRelationshipAndRuntimeStory(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:payments", Name: "payments"}
	got := buildRepositoryStoryResponse(
		repo,
		42,
		[]string{"go"},
		[]string{"payments-api"},
		[]string{"ecs_service"},
		1,
		map[string]any{
			"families": []string{"docker"},
			"relationship_overview": map[string]any{
				"relationship_count": 1,
				"story":              "IaC-driven relationships: DEPLOYS_FROM payments-service via dockerfile_source_label.",
				"iac_driven": []map[string]any{
					{
						"type":          "DEPLOYS_FROM",
						"target_name":   "payments-service",
						"target_id":     "repo-7",
						"evidence_type": "dockerfile_source_label",
					},
				},
			},
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
		nil,
	)

	story, ok := got["story"].(string)
	if !ok {
		t.Fatalf("story type = %T, want string", got["story"])
	}
	if story == "" {
		t.Fatal("story is empty, want combined narrative")
	}
	if want := "dockerfile_source_label"; !containsSubstring(story, want) {
		t.Fatalf("story = %q, want %q", story, want)
	}

	relationshipOverview, ok := got["relationship_overview"].(map[string]any)
	if !ok {
		t.Fatalf("relationship_overview type = %T, want map[string]any", got["relationship_overview"])
	}
	if got, want := relationshipOverview["relationship_count"], 1; got != want {
		t.Fatalf("relationship_overview.relationship_count = %#v, want %#v", got, want)
	}

	deploymentOverview, ok := got["deployment_overview"].(map[string]any)
	if !ok {
		t.Fatalf("deployment_overview type = %T, want map[string]any", got["deployment_overview"])
	}
	directStory, ok := deploymentOverview["direct_story"].([]string)
	if !ok {
		t.Fatalf("direct_story type = %T, want []string", deploymentOverview["direct_story"])
	}
	if len(directStory) != 1 {
		t.Fatalf("len(direct_story) = %d, want 1", len(directStory))
	}
	if got, want := directStory[0], "Runtime artifacts include dockerfile stage runtime in Dockerfile based on alpine with cmd [\"/app\", \"--serve\"] (base_image, copy_from, cmd, ports)."; got != want {
		t.Fatalf("direct_story[0] = %q, want %q", got, want)
	}
}

func TestBuildRepositoryStoryResponsePreservesTerragruntNestedConfigStory(t *testing.T) {
	t.Parallel()

	configArtifacts := buildRepositoryConfigArtifacts("terragrunt-deployment", []FileContent{
		{
			RelativePath: "accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl",
			Content: `include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  path_parts   = split("/", path_relative_to_include("root"))
  account_name = local.path_parts[1]
  region_name  = local.path_parts[2]
  vpc_name     = local.path_parts[3]

  inherited    = read_terragrunt_config(find_in_parent_folders("env.hcl"))
  account_vars = yamldecode(file("${get_repo_root()}/accounts/${local.account_name}/account.yaml"))
  region_vars  = yamldecode(file("${get_repo_root()}/accounts/${local.account_name}/${local.region_name}/region.yaml"))
}
`,
		},
	})
	if configArtifacts == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths, ok := configArtifacts["config_paths"].([]map[string]any)
	if !ok {
		t.Fatalf("config_paths type = %T, want []map[string]any", configArtifacts["config_paths"])
	}

	repo := RepoRef{ID: "repository:terragrunt-deployment", Name: "terragrunt-deployment"}
	got := buildRepositoryStoryResponse(
		repo,
		12,
		[]string{"hcl"},
		nil,
		nil,
		0,
		map[string]any{
			"families": []string{"terragrunt", "terraform"},
			"deployment_artifacts": map[string]any{
				"config_paths": configPaths,
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

	wantLines := []string{
		"Config provenance includes accounts/bg-dev/account.yaml from terragrunt-deployment via local_config_asset in accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl.",
		"Config provenance includes accounts/bg-dev/us-east-1/region.yaml from terragrunt-deployment via local_config_asset in accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl.",
		"Config provenance includes env.hcl from terragrunt-deployment via terragrunt_find_in_parent_folders in accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl.",
		"Config provenance includes env.hcl from terragrunt-deployment via terragrunt_read_config in accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl.",
		"Config provenance includes root.hcl from terragrunt-deployment via terragrunt_include_path in accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl.",
	}
	for _, want := range wantLines {
		if !containsExactLine(directStory, want) {
			t.Fatalf("direct_story = %#v, want line %q", directStory, want)
		}
	}
}

func TestBuildRepositoryStoryResponsePreservesSharedConfigAlongsideDeliverySurfaces(t *testing.T) {
	t.Parallel()

	repo := RepoRef{ID: "repository:platform-service", Name: "platform-service"}
	got := buildRepositoryStoryResponse(
		repo,
		64,
		[]string{"go", "yaml"},
		[]string{"platform-runtime"},
		[]string{"argocd_application", "github_actions"},
		5,
		map[string]any{
			"families": []string{"argocd", "ansible", "github_actions", "docker_compose", "terraform"},
			"deployment_artifacts": map[string]any{
				"controller_artifacts": []map[string]any{
					{
						"path":             "Jenkinsfile",
						"controller_kind":  "jenkins_pipeline",
						"shared_libraries": []string{"pipelines"},
						"entry_points":     []string{"dist/api.js"},
					},
				},
				"workflow_artifacts": []map[string]any{
					{
						"relative_path": ".github/workflows/deploy.yaml",
						"artifact_type": "github_actions_workflow",
						"workflow_name": "deploy",
						"signals":       []string{"workflow_file"},
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

	wantLines := []string{
		"Workflow delivery paths include .github/workflows/deploy.yaml as github_actions_workflow deploy (workflow_file).",
		"Controller delivery paths include Jenkinsfile via jenkins_pipeline (entry points dist/api.js; shared libraries pipelines).",
		"Runtime artifacts include docker_compose service api in docker-compose.yaml built from ./ (build, ports).",
		"Shared config families span /configd/payments/* across helm-charts, terraform-stack-payments.",
	}
	for _, want := range wantLines {
		if !containsExactLine(directStory, want) {
			t.Fatalf("direct_story = %#v, want line %q", directStory, want)
		}
	}
}

func containsExactLine(lines []string, want string) bool {
	for _, line := range lines {
		if line == want {
			return true
		}
	}
	return false
}
