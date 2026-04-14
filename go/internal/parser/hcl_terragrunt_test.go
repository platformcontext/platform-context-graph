package parser

import (
	"path/filepath"
	"testing"

	"github.com/hashicorp/hcl/v2/hclparse"
	"github.com/hashicorp/hcl/v2/hclsyntax"
)

func TestParseTerragruntTerraformSourceMaterializesModuleSource(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "terragrunt.hcl")
	source := []byte(`terraform {
  source = "../modules/app"
}

include "root" {
  path = find_in_parent_folders()
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
	if config["terraform_source"] != "../modules/app" {
		t.Fatalf("terraform_source = %#v, want %#v", config["terraform_source"], "../modules/app")
	}

	rows := parseTerragruntModuleSources(body, source, filePath)
	if len(rows) != 1 {
		t.Fatalf("len(rows) = %d, want 1", len(rows))
	}
	if rows[0]["name"] != "terragrunt" {
		t.Fatalf("name = %#v, want %#v", rows[0]["name"], "terragrunt")
	}
	if rows[0]["source"] != "../modules/app" {
		t.Fatalf("source = %#v, want %#v", rows[0]["source"], "../modules/app")
	}
}
