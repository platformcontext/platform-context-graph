package query

import "testing"

func TestBuildRepositoryConfigArtifactsExtractsLookupBackedTemplateAssetsWithTrimspaceWrapper(t *testing.T) {
	t.Parallel()

	got := buildRepositoryConfigArtifacts("terraform-modules-aws", []FileContent{
		{
			RelativePath: "modules/autoscaling/main.tf",
			Content: `locals {
  userdata_template = lookup(
    var.configuration,
    "userdata_template",
    "${path.module}/templates/user_data.tpl",
  )
  dashboard_template = lookup(
    var.configuration,
    "dashboard_template",
    "${path.module}/templates/cloudwatch-dashboard.tpl",
  )

  userdata = trimspace(templatefile(local.userdata_template, {
    userdata = var.user_data
  }))
  cloudwatch_dashboard = templatefile(local.dashboard_template, {
    name = var.name
  })
}
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryConfigArtifacts() = nil, want config_paths")
	}

	configPaths := mapSliceValue(got, "config_paths")
	if len(configPaths) != 2 {
		t.Fatalf("len(config_paths) = %d, want 2", len(configPaths))
	}

	wantPaths := []string{"templates/cloudwatch-dashboard.tpl", "templates/user_data.tpl"}
	for index, want := range wantPaths {
		if got, ok := configPaths[index]["path"].(string); !ok || got != want {
			t.Fatalf("config_paths[%d].path = %#v, want %#v", index, configPaths[index]["path"], want)
		}
		if got, wantRepo := configPaths[index]["source_repo"], "terraform-modules-aws"; got != wantRepo {
			t.Fatalf("config_paths[%d].source_repo = %#v, want %#v", index, got, wantRepo)
		}
		if got, wantRelative := configPaths[index]["relative_path"], "modules/autoscaling/main.tf"; got != wantRelative {
			t.Fatalf("config_paths[%d].relative_path = %#v, want %#v", index, got, wantRelative)
		}
		if got, wantKind := configPaths[index]["evidence_kind"], "local_config_asset"; got != wantKind {
			t.Fatalf("config_paths[%d].evidence_kind = %#v, want %#v", index, got, wantKind)
		}
	}
}
