package reducer

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestApplyResolvedDeploymentSourcesReclassifiesControllerCandidateAsService(t *testing.T) {
	t.Parallel()

	candidates := []WorkloadCandidate{
		{
			RepoID:         "repo-api",
			RepoName:       "api-service",
			Classification: "utility",
			Confidence:     0.42,
			Provenance:     []string{"jenkins_pipeline"},
		},
	}
	resolved := []relationships.ResolvedRelationship{
		{
			SourceRepoID:     "repo-deploy",
			TargetRepoID:     "repo-api",
			RelationshipType: relationships.RelDeploysFrom,
			Confidence:       0.9,
			ResolutionSource: "test",
			Details: map[string]any{
				"evidence_kinds": []string{string(relationships.EvidenceKindKustomizeResource)},
			},
		},
	}

	enriched := applyResolvedDeploymentSources(candidates, resolved)
	if len(enriched) != 1 {
		t.Fatalf("len(enriched) = %d, want 1", len(enriched))
	}
	candidate := enriched[0]
	if got, want := candidate.DeploymentRepoID, "repo-deploy"; got != want {
		t.Fatalf("DeploymentRepoID = %q, want %q", got, want)
	}
	if got, want := candidate.Classification, "service"; got != want {
		t.Fatalf("Classification = %q, want %q after deployment evidence enrichment", got, want)
	}
	if got, want := candidate.Confidence, 0.9; got != want {
		t.Fatalf("Confidence = %f, want %f", got, want)
	}
	if !hasProvenance(candidate.Provenance, "kustomize_resource") {
		t.Fatalf("Provenance = %v, want kustomize_resource", candidate.Provenance)
	}
}
