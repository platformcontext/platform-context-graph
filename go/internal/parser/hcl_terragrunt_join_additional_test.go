package parser

import (
	"path/filepath"
	"testing"

	"github.com/hashicorp/hcl/v2/hclparse"
	"github.com/hashicorp/hcl/v2/hclsyntax"
)

func TestParseTerragruntConfigExtractsRepoRootAndPathModuleJoinedHelperPaths(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "terragrunt.hcl")
	source := []byte(`locals {
  runtime = yamldecode(file(join("/", [get_repo_root(), "config/runtime.yaml"])))
  rendered = templatefile(join("/", [path.module, "templates/runtime.json"]), {})
}
`)

	file, diags := hclparse.NewParser().ParseHCL(source, filePath)
	if diags.HasErrors() {
		t.Fatalf("ParseHCL() diagnostics = %s", diags.Error())
	}
	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		t.Fatalf("file.Body = %T, want *hclsyntax.Body", file.Body)
	}

	config := parseTerragruntConfig(body, source, filePath)

	if got, want := config["local_config_asset_paths"], "config/runtime.yaml,templates/runtime.json"; got != want {
		t.Fatalf("local_config_asset_paths = %#v, want %#v", got, want)
	}
}

func TestParseTerragruntConfigResolvesLocalInterpolationsInJoinedHelperPaths(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "terragrunt.hcl")
	source := []byte(`locals {
  account_name = "bg-dev"
  account_vars = yamldecode(file(join("/", [get_repo_root(), "accounts/${local.account_name}/account.yaml"])))
}
`)

	file, diags := hclparse.NewParser().ParseHCL(source, filePath)
	if diags.HasErrors() {
		t.Fatalf("ParseHCL() diagnostics = %s", diags.Error())
	}
	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		t.Fatalf("file.Body = %T, want *hclsyntax.Body", file.Body)
	}

	config := parseTerragruntConfig(body, source, filePath)

	if got, want := config["local_config_asset_paths"], "accounts/bg-dev/account.yaml"; got != want {
		t.Fatalf("local_config_asset_paths = %#v, want %#v", got, want)
	}
}

func TestParseTerragruntConfigResolvesNestedLocalBackedHelperPaths(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "terragrunt.hcl")
	source := []byte(`locals {
  container_template = var.platform_capabilities[0] == "FARGATE" ? "container-fargate.tpl" : "container-ec2.tpl"

  container_properties = templatefile(lookup(var.configuration, "template", "${path.module}/batch/${local.container_template}"), {
    name = var.name
  })
}
`)

	file, diags := hclparse.NewParser().ParseHCL(source, filePath)
	if diags.HasErrors() {
		t.Fatalf("ParseHCL() diagnostics = %s", diags.Error())
	}
	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		t.Fatalf("file.Body = %T, want *hclsyntax.Body", file.Body)
	}

	config := parseTerragruntConfig(body, source, filePath)

	if got, want := config["local_config_asset_paths"], "batch/container-fargate.tpl"; got != want {
		t.Fatalf("local_config_asset_paths = %#v, want %#v", got, want)
	}
}
