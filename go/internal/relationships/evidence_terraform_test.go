package relationships

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestDiscoverTerraformLocalModuleSourceEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-fsbo",
			Payload: map[string]any{
				"artifact_type": "terraform_hcl",
				"relative_path": "environments/bg-qa/prod_braintree_keys.tf",
				"content": `module "api_key_default" {
  source = "../../local-modules/braintree-api"
}
`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-braintree-api", Aliases: []string{"braintree-api"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)
	if len(evidence) != 1 {
		t.Fatalf("len(evidence) = %d, want 1", len(evidence))
	}
	if got, want := evidence[0].EvidenceKind, EvidenceKindTerraformModuleSource; got != want {
		t.Fatalf("EvidenceKind = %q, want %q", got, want)
	}
	if got, want := evidence[0].RelationshipType, RelUsesModule; got != want {
		t.Fatalf("RelationshipType = %q, want %q", got, want)
	}
	if got, want := evidence[0].TargetRepoID, "repo-braintree-api"; got != want {
		t.Fatalf("TargetRepoID = %q, want %q", got, want)
	}
	if got, want := evidence[0].Details["source_ref"], "../../local-modules/braintree-api"; got != want {
		t.Fatalf("source_ref = %#v, want %#v", got, want)
	}
}

func TestDiscoverTerraformRegistryMonorepoModuleSourceEvidence(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name         string
		artifactType string
		relativePath string
		content      string
	}{
		{
			name:         "terraform module source maps to aws monorepo",
			artifactType: "terraform_hcl",
			relativePath: "shared/pending-provisioning.tf",
			content: `module "queue" {
  source = "boatsgroup.pe.jfrog.io/TF__BG/lambda-function/aws"
}
`,
		},
		{
			name:         "terragrunt terraform source maps to aws monorepo",
			artifactType: "terragrunt",
			relativePath: "env/dev/terragrunt.hcl",
			content: `terraform {
  source = "boatsgroup.pe.jfrog.io/TF__BG/ecs-application/aws"
}
`,
		},
	}

	catalog := []CatalogEntry{
		{RepoID: "repo-terraform-modules-aws", Aliases: []string{"terraform-modules-aws"}},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			envelopes := []facts.Envelope{
				{
					ScopeID: "repo-stack",
					Payload: map[string]any{
						"artifact_type": tt.artifactType,
						"relative_path": tt.relativePath,
						"content":       tt.content,
					},
				},
			}

			evidence := DiscoverEvidence(envelopes, catalog)
			if len(evidence) != 1 {
				t.Fatalf("len(evidence) = %d, want 1", len(evidence))
			}
			if got, want := evidence[0].EvidenceKind, EvidenceKindTerraformModuleSource; got != want {
				t.Fatalf("EvidenceKind = %q, want %q", got, want)
			}
			if got, want := evidence[0].RelationshipType, RelUsesModule; got != want {
				t.Fatalf("RelationshipType = %q, want %q", got, want)
			}
			if got, want := evidence[0].TargetRepoID, "repo-terraform-modules-aws"; got != want {
				t.Fatalf("TargetRepoID = %q, want %q", got, want)
			}
		})
	}
}

func TestDiscoverTerraformAndTerragruntHelperBuiltPathEvidence(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name         string
		artifactType string
		relativePath string
		parsedData   map[string]any
		catalog      []CatalogEntry
		wantKind     EvidenceKind
		wantTarget   string
	}{
		{
			name:         "helper-built terraform source maps to module repository",
			artifactType: "terraform_hcl",
			relativePath: "shared/pending-provisioning.tf",
			parsedData: map[string]any{
				"terraform_modules": []any{
					map[string]any{
						"name":   "queue",
						"source": `join("/", [get_repo_root(), "local-modules/braintree-api"])`,
					},
				},
			},
			catalog: []CatalogEntry{
				{RepoID: "repo-braintree-api", Aliases: []string{"braintree-api"}},
			},
			wantKind:   EvidenceKindTerraformModuleSource,
			wantTarget: "repo-braintree-api",
		},
		{
			name:         "helper-built terragrunt dependency config path maps to target repository",
			artifactType: "terragrunt",
			relativePath: "env/dev/terragrunt.hcl",
			parsedData: map[string]any{
				"terragrunt_dependencies": []any{
					map[string]any{
						"name":        "payments",
						"config_path": `join("/", [get_repo_root(), "payments-service"])`,
					},
				},
			},
			catalog: []CatalogEntry{
				{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
			},
			wantKind:   EvidenceKindTerragruntDependencyConfigPath,
			wantTarget: "repo-payments",
		},
	}

	for _, tt := range tests {
		tt := tt
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()

			evidence := DiscoverEvidence([]facts.Envelope{
				{
					ScopeID: "repo-stack",
					Payload: map[string]any{
						"artifact_type":    tt.artifactType,
						"relative_path":    tt.relativePath,
						"parsed_file_data": tt.parsedData,
					},
				},
			}, tt.catalog)
			if len(evidence) != 1 {
				t.Fatalf("len(evidence) = %d, want 1", len(evidence))
			}
			if got, want := evidence[0].EvidenceKind, tt.wantKind; got != want {
				t.Fatalf("EvidenceKind = %q, want %q", got, want)
			}
			if got, want := evidence[0].TargetRepoID, tt.wantTarget; got != want {
				t.Fatalf("TargetRepoID = %q, want %q", got, want)
			}
		})
	}
}
