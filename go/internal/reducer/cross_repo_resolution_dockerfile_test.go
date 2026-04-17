package reducer

import (
	"context"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestCrossRepoResolutionPromotesDockerfileSourceLabelToCanonicalDeploysFrom(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindDockerfileSourceLabel,
					RelationshipType: relationships.RelDeploysFrom,
					SourceRepoID:     "repo-runtime",
					TargetRepoID:     "repo-payments",
					Confidence:       0.93,
				},
			},
		},
		EdgeWriter: edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-dockerfile", "gen-dockerfile")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1", count)
	}
	if len(edgeWriter.writeCalls) != 1 || len(edgeWriter.writeCalls[0].rows) != 1 {
		t.Fatalf("writeCalls = %#v, want 1 row", edgeWriter.writeCalls)
	}

	row := edgeWriter.writeCalls[0].rows[0]
	if got, want := stringValue(row.Payload["relationship_type"]), string(relationships.RelDeploysFrom); got != want {
		t.Fatalf("relationship_type = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["target_repo_id"]), "repo-payments"; got != want {
		t.Fatalf("target_repo_id = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["evidence_type"]), "dockerfile_source_label"; got != want {
		t.Fatalf("evidence_type = %q, want %q", got, want)
	}
}
