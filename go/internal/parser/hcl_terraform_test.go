package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathHCLTerraformBlockMetadata(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "main.tf")
	writeTestFile(
		t,
		filePath,
		`terraform {
  required_providers {
    aws = {
      source = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "terraform_blocks", "terraform")
	assertBucketContainsFieldValue(t, got, "terraform_blocks", "required_providers", "aws")
	assertBucketContainsFieldValue(t, got, "terraform_blocks", "required_provider_sources", "aws=hashicorp/aws")

	blocks, ok := got["terraform_blocks"].([]map[string]any)
	if !ok {
		t.Fatalf("terraform_blocks = %T, want []map[string]any", got["terraform_blocks"])
	}
	if len(blocks) != 1 {
		t.Fatalf("len(terraform_blocks) = %d, want 1", len(blocks))
	}
	if got, want := blocks[0]["required_provider_count"], 1; got != want {
		t.Fatalf("terraform_blocks[0].required_provider_count = %#v, want %#v", got, want)
	}
}
