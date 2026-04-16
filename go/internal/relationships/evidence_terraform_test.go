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
