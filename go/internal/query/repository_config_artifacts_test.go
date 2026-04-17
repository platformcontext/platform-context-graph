package query

import "testing"

func TestBuildRepositoryConfigArtifactsExtractsKustomizePolicyConfigPaths(t *testing.T) {
	t.Parallel()

	files := []FileContent{
		{
			RelativePath: "deploy/kustomization.yaml",
			Content: `apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources:
  - policy.yaml
`,
		},
		{
			RelativePath: "deploy/policy.yaml",
			Content: `apiVersion: iam.aws.upbound.io/v1beta1
kind: RolePolicy
spec:
  policyDocument:
    Statement:
      - Effect: Allow
        Action:
          - ssm:GetParameter
        Resource:
          - arn:aws:ssm:us-east-1:123456789012:parameter/configd/payments/*
          - /api/payments/runtime/*
`,
		},
		{
			RelativePath: "deploy/unreachable.yaml",
			Content: `apiVersion: iam.aws.upbound.io/v1beta1
kind: RolePolicy
spec:
  policyDocument:
    Statement:
      - Resource:
          - arn:aws:ssm:us-east-1:123456789012:parameter/configd/ignored/*
`,
		},
	}

	got := buildRepositoryConfigArtifacts("helm-charts", files)
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 2 {
		t.Fatalf("len(config_paths) = %d, want 2", len(configPaths))
	}

	if got, want := configPaths[0]["path"], "/api/payments/runtime/*"; got != want {
		t.Fatalf("config_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["source_repo"], "helm-charts"; got != want {
		t.Fatalf("config_paths[0].source_repo = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["relative_path"], "deploy/policy.yaml"; got != want {
		t.Fatalf("config_paths[0].relative_path = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["evidence_kind"], "kustomize_policy_document_resource"; got != want {
		t.Fatalf("config_paths[0].evidence_kind = %#v, want %#v", got, want)
	}

	if got, want := configPaths[1]["path"], "/configd/payments/*"; got != want {
		t.Fatalf("config_paths[1].path = %#v, want %#v", got, want)
	}
}

func TestBuildRepositoryConfigArtifactsExtractsTerragruntDependencyConfigPaths(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("terraform-stack-payments", []FileContent{
		{
			RelativePath: "env/prod/terragrunt.hcl",
			Content: `terraform {
  source = "../modules/service"
}

dependency "network" {
  config_path = "../network"
}
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 1 {
		t.Fatalf("len(config_paths) = %d, want 1", len(configPaths))
	}
	if got, want := configPaths[0]["path"], "../network"; got != want {
		t.Fatalf("config_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["source_repo"], "terraform-stack-payments"; got != want {
		t.Fatalf("config_paths[0].source_repo = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["evidence_kind"], "terragrunt_dependency_config_path"; got != want {
		t.Fatalf("config_paths[0].evidence_kind = %#v, want %#v", got, want)
	}
}

func TestBuildRepositoryConfigArtifactsExtractsTerragruntAndTerraformConfigAssets(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("terraform-stack-payments", []FileContent{
		{
			RelativePath: "env/prod/terragrunt.hcl",
			Content: `include "root" {
  path = find_in_parent_folders("root.hcl")
}

locals {
  env = read_terragrunt_config(find_in_parent_folders("env.hcl"))
}

inputs = yamldecode(file("${get_repo_root()}/config/runtime.yaml"))
`,
		},
		{
			RelativePath: "modules/build/main.tf",
			Content: `resource "aws_codebuild_project" "build" {
  buildspec = file("${path.module}/buildspec.yaml")
}

locals {
  rendered = templatefile("${path.module}/templates/runtime.json", {})
}

module "service" {
  source = "./modules/service"
}
`,
		},
		{
			RelativePath: "env/prod/terraform.tfvars",
			Content: `app_repo = "payments-service"
`,
		},
		{
			RelativePath: "env/prod/terraform.tfvars.json",
			Content:      `{"app_repo":"payments-service"}`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	wantPaths := []string{
		"buildspec.yaml",
		"config/runtime.yaml",
		"env.hcl",
		"env.hcl",
		"env/prod/terraform.tfvars",
		"env/prod/terraform.tfvars.json",
		"modules/service",
		"root.hcl",
		"root.hcl",
		"templates/runtime.json",
	}
	if len(configPaths) != len(wantPaths) {
		t.Fatalf("len(config_paths) = %d, want %d", len(configPaths), len(wantPaths))
	}
	for index, want := range wantPaths {
		if got, ok := configPaths[index]["path"].(string); !ok || got != want {
			t.Fatalf("config_paths[%d].path = %#v, want %#v", index, configPaths[index]["path"], want)
		}
	}
}

func TestBuildRepositoryConfigArtifactsExtractsTerragruntFindInParentFoldersSidecars(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("iac-terragrunt-core-infra", []FileContent{
		{
			RelativePath: "aws/accounts/ops-qa/us-east-1/ops-qa.network-us-east-1/root.hcl",
			Content: `locals {
  global_vars = try(
    yamldecode(file("${path_relative_to_include()}/global.yaml")),
    yamldecode(file(find_in_parent_folders("global.yaml"))),
    {}
  )
  account_vars = try(
    yamldecode(file(find_in_parent_folders("account.yaml"))),
    {}
  )
  region_vars = try(
    yamldecode(file(find_in_parent_folders("region.yaml"))),
    {}
  )
  env_vars = try(
    yamldecode(file(find_in_parent_folders("env.yaml"))),
    {}
  )
}
`,
		},
		{
			RelativePath: "aws/accounts/ops-qa/us-east-1/ops-qa.network-us-east-1/services/ops-qa-eks/terragrunt.hcl",
			Content: `include "root" {
  path = find_in_parent_folders("root.hcl")
}
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 7 {
		t.Fatalf("len(config_paths) = %d, want 7", len(configPaths))
	}

	pathCounts := map[string]int{}
	evidenceKinds := map[string]map[string]int{}
	for _, row := range configPaths {
		if got, want := row["source_repo"], "iac-terragrunt-core-infra"; got != want {
			t.Fatalf("config_paths row source_repo = %#v, want %#v", got, want)
		}
		path, _ := row["path"].(string)
		kind, _ := row["evidence_kind"].(string)
		pathCounts[path]++
		if evidenceKinds[path] == nil {
			evidenceKinds[path] = map[string]int{}
		}
		evidenceKinds[path][kind]++
	}

	wantCounts := map[string]int{
		"account.yaml": 1,
		"env.yaml":     1,
		"global.yaml":  2,
		"region.yaml":  1,
		"root.hcl":     2,
	}
	for path, want := range wantCounts {
		if got := pathCounts[path]; got != want {
			t.Fatalf("pathCounts[%q] = %d, want %d", path, got, want)
		}
	}
	if got := evidenceKinds["global.yaml"]["local_config_asset"]; got != 1 {
		t.Fatalf("global.yaml local_config_asset count = %d, want 1", got)
	}
	if got := evidenceKinds["global.yaml"]["terragrunt_find_in_parent_folders"]; got != 1 {
		t.Fatalf("global.yaml terragrunt_find_in_parent_folders count = %d, want 1", got)
	}
	if got := evidenceKinds["root.hcl"]["terragrunt_find_in_parent_folders"]; got != 1 {
		t.Fatalf("root.hcl terragrunt_find_in_parent_folders count = %d, want 1", got)
	}
	if got := evidenceKinds["root.hcl"]["terragrunt_include_path"]; got != 1 {
		t.Fatalf("root.hcl terragrunt_include_path count = %d, want 1", got)
	}
}

func TestBuildRepositoryConfigArtifactsExtractsDefaultTerragruntParentConfig(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("iac-terragrunt-core-infra", []FileContent{
		{
			RelativePath: "modules/eks/terragrunt.hcl",
			Content: `include "root" {
  path = find_in_parent_folders()
}

locals {
  inherited = read_terragrunt_config(find_in_parent_folders())
}
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 3 {
		t.Fatalf("len(config_paths) = %d, want 3", len(configPaths))
	}

	pathCounts := map[string]int{}
	evidenceKinds := map[string]map[string]int{}
	for _, row := range configPaths {
		path, _ := row["path"].(string)
		kind, _ := row["evidence_kind"].(string)
		pathCounts[path]++
		if evidenceKinds[path] == nil {
			evidenceKinds[path] = map[string]int{}
		}
		evidenceKinds[path][kind]++
	}

	if got, want := pathCounts["terragrunt.hcl"], 3; got != want {
		t.Fatalf("pathCounts[terragrunt.hcl] = %d, want %d", got, want)
	}
	if got, want := evidenceKinds["terragrunt.hcl"]["terragrunt_include_path"], 1; got != want {
		t.Fatalf("terragrunt.hcl terragrunt_include_path count = %d, want %d", got, want)
	}
	if got, want := evidenceKinds["terragrunt.hcl"]["terragrunt_read_config"], 1; got != want {
		t.Fatalf("terragrunt.hcl terragrunt_read_config count = %d, want %d", got, want)
	}
	if got, want := evidenceKinds["terragrunt.hcl"]["terragrunt_find_in_parent_folders"], 1; got != want {
		t.Fatalf("terragrunt.hcl terragrunt_find_in_parent_folders count = %d, want %d", got, want)
	}
}

func TestBuildRepositoryConfigArtifactsExtractsAnsibleConfigAssets(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("ansible-ops", []FileContent{
		{
			RelativePath: "playbooks/site.yml",
			Content: `- hosts: all
  roles:
    - web
`,
		},
		{
			RelativePath: "inventories/prod/hosts.yml",
			Content: `all:
  children:
    web:
      hosts:
        web-1.example.com:
`,
		},
		{
			RelativePath: "group_vars/all.yml",
			Content:      "app_name: demo\n",
		},
		{
			RelativePath: "roles/web/tasks/main.yml",
			Content:      "- debug:\n    msg: hello\n",
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want ansible config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 5 {
		t.Fatalf("len(config_paths) = %d, want 5", len(configPaths))
	}

	want := map[string]string{
		"playbooks/site.yml":         "ansible_playbook",
		"inventories/prod/hosts.yml": "ansible_inventory",
		"group_vars/all.yml":         "ansible_vars",
		"roles/web":                  "ansible_role",
		"roles/web/tasks/main.yml":   "ansible_task_entrypoint",
	}
	for _, row := range configPaths {
		path, _ := row["path"].(string)
		if path == "" {
			t.Fatalf("config_paths row missing path: %#v", row)
		}
		if gotKind, ok := row["evidence_kind"].(string); !ok || gotKind != want[path] {
			t.Fatalf("config_paths[%q].evidence_kind = %#v, want %#v", path, row["evidence_kind"], want[path])
		}
		if gotRepo, ok := row["source_repo"].(string); !ok || gotRepo != "ansible-ops" {
			t.Fatalf("config_paths[%q].source_repo = %#v, want %q", path, row["source_repo"], "ansible-ops")
		}
	}
}
