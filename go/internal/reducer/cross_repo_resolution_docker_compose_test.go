package reducer

import (
	"context"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestCrossRepoResolutionPromotesDockerComposeEvidenceToCanonicalDeploysFrom(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindDockerComposeImage,
					RelationshipType: relationships.RelDeploysFrom,
					SourceRepoID:     "repo-deploy",
					TargetRepoID:     "repo-checkout",
					Confidence:       0.88,
				},
			},
		},
		EdgeWriter: edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1", count)
	}
	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("write call count = %d, want 1", len(edgeWriter.writeCalls))
	}
	if got, want := edgeWriter.writeCalls[0].evidenceSource, crossRepoEvidenceSource; got != want {
		t.Fatalf("evidenceSource = %q, want %q", got, want)
	}
	rows := edgeWriter.writeCalls[0].rows
	if len(rows) != 1 {
		t.Fatalf("write row count = %d, want 1", len(rows))
	}
	row := rows[0]
	if got, want := stringValue(row.Payload["relationship_type"]), string(relationships.RelDeploysFrom); got != want {
		t.Fatalf("relationship_type = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["target_repo_id"]), "repo-checkout"; got != want {
		t.Fatalf("target_repo_id = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["evidence_source"]), crossRepoEvidenceSource; got != want {
		t.Fatalf("payload evidence_source = %q, want %q", got, want)
	}
}

func TestCrossRepoResolutionPromotesDockerComposeBuildContextToCanonicalDeploysFrom(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindDockerComposeBuildContext,
					RelationshipType: relationships.RelDeploysFrom,
					SourceRepoID:     "repo-compose",
					TargetRepoID:     "repo-build-context",
					Confidence:       0.91,
				},
			},
		},
		EdgeWriter: edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-build", "gen-build")
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
	if got, want := stringValue(row.Payload["target_repo_id"]), "repo-build-context"; got != want {
		t.Fatalf("target_repo_id = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["evidence_type"]), "docker_compose_build_context"; got != want {
		t.Fatalf("evidence_type = %q, want %q", got, want)
	}
}

func TestCrossRepoResolutionPromotesDockerComposeDependsOnToCanonicalDependency(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindDockerComposeDependsOn,
					RelationshipType: relationships.RelDependsOn,
					SourceRepoID:     "repo-compose",
					TargetRepoID:     "repo-runtime",
					Confidence:       0.84,
				},
			},
		},
		EdgeWriter: edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-depends", "gen-depends")
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
	if got, want := stringValue(row.Payload["relationship_type"]), string(relationships.RelDependsOn); got != want {
		t.Fatalf("relationship_type = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["target_repo_id"]), "repo-runtime"; got != want {
		t.Fatalf("target_repo_id = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["evidence_type"]), "docker_compose_depends_on"; got != want {
		t.Fatalf("evidence_type = %q, want %q", got, want)
	}
}
