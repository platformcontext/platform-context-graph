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
