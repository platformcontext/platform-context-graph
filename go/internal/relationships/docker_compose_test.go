package relationships

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestDiscoverDockerComposeEvidencePromotesBuildContextAndImageReferences(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			ScopeID: "repo-deploy",
			Payload: map[string]any{
				"artifact_type": "docker_compose",
				"relative_path": "docker-compose.yaml",
				"content": `services:
  payments:
    build:
      context: ../payments-service
  checkout:
    image: ghcr.io/myorg/checkout-service:latest
`,
			},
		},
	}
	catalog := []CatalogEntry{
		{RepoID: "repo-payments", Aliases: []string{"payments-service"}},
		{RepoID: "repo-checkout", Aliases: []string{"checkout-service"}},
	}

	evidence := DiscoverEvidence(envelopes, catalog)
	if len(evidence) != 2 {
		t.Fatalf("len = %d, want 2", len(evidence))
	}

	got := make(map[EvidenceKind]EvidenceFact, len(evidence))
	for _, fact := range evidence {
		if fact.RelationshipType != RelDeploysFrom {
			t.Fatalf("relationship_type = %q, want %q", fact.RelationshipType, RelDeploysFrom)
		}
		got[fact.EvidenceKind] = fact
	}

	buildContext, ok := got[EvidenceKindDockerComposeBuildContext]
	if !ok {
		t.Fatal("missing docker compose build-context evidence")
	}
	if got, want := buildContext.TargetRepoID, "repo-payments"; got != want {
		t.Fatalf("build context target = %q, want %q", got, want)
	}
	if got, want := buildContext.Details["build_context"], "../payments-service"; got != want {
		t.Fatalf("build context details = %#v, want %#v", got, want)
	}

	imageRef, ok := got[EvidenceKindDockerComposeImage]
	if !ok {
		t.Fatal("missing docker compose image evidence")
	}
	if got, want := imageRef.TargetRepoID, "repo-checkout"; got != want {
		t.Fatalf("image ref target = %q, want %q", got, want)
	}
	if got, want := imageRef.Details["image_ref"], "ghcr.io/myorg/checkout-service:latest"; got != want {
		t.Fatalf("image ref details = %#v, want %#v", got, want)
	}
}
