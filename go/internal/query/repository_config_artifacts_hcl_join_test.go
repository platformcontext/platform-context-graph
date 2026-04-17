package query

import "testing"

func TestBuildRepositoryConfigArtifactsExtractsSlashJoinedPathModuleTemplateAssets(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("terraform-stack-aws-client-vpn", []FileContent{
		{
			RelativePath: "modules/2024.02/custom/ecs-application/pipeline_node/main.tf",
			Content: `locals {
  appspec_yaml_file = templatefile(join("/", [path.module, "specs/AppSpec.yaml"]), {
    app_name = var.app_name
  })
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
	if got, want := configPaths[0]["path"], "specs/AppSpec.yaml"; got != want {
		t.Fatalf("config_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["evidence_kind"], "local_config_asset"; got != want {
		t.Fatalf("config_paths[0].evidence_kind = %#v, want %#v", got, want)
	}
}

func TestBuildRepositoryConfigArtifactsExtractsSlashJoinedRepoRootAssets(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("terragrunt-deployment", []FileContent{
		{
			RelativePath: "accounts/bg-dev/us-east-1/dev.network-us-east-1/services/terragrunt.hcl",
			Content: `locals {
  account_name = "bg-dev"
  account_vars = yamldecode(file(join("/", [get_repo_root(), "accounts/${local.account_name}/account.yaml"])))
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
	if got, want := configPaths[0]["path"], "accounts/bg-dev/account.yaml"; got != want {
		t.Fatalf("config_paths[0].path = %#v, want %#v", got, want)
	}
	if got, want := configPaths[0]["evidence_kind"], "local_config_asset"; got != want {
		t.Fatalf("config_paths[0].evidence_kind = %#v, want %#v", got, want)
	}
}
