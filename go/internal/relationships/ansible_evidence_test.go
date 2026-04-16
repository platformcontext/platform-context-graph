package relationships

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestDiscoverAnsibleRoleReferenceEvidence(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-ops",
			Payload: map[string]any{
				"artifact_type": "ansible_playbook",
				"relative_path": "playbooks/site.yml",
				"content": `- hosts: all
  roles:
    - role: payments-service
      src: git+https://github.com/myorg/payments-service.git
`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)
	if len(evidence) != 1 {
		t.Fatalf("len = %d, want 1", len(evidence))
	}
	if evidence[0].EvidenceKind != EvidenceKindAnsibleRoleReference {
		t.Fatalf("kind = %q, want %q", evidence[0].EvidenceKind, EvidenceKindAnsibleRoleReference)
	}
	if evidence[0].RelationshipType != RelDependsOn {
		t.Fatalf("type = %q, want %q", evidence[0].RelationshipType, RelDependsOn)
	}
	if evidence[0].TargetRepoID != "repo-payments" {
		t.Fatalf("target = %q, want repo-payments", evidence[0].TargetRepoID)
	}
}
