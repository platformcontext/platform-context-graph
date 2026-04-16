package reducer

import (
	"context"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestCrossRepoResolutionPromotesTerraformVariableFileEvidence(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
					RelationshipType: relationships.RelProvisionsDependencyFor,
					SourceRepoID:     "repo-live",
					TargetRepoID:     "repo-payments",
					Confidence:       0.99,
					Rationale:        "Terraform app_repo points at the target repository",
					Details: map[string]any{
						"path":          "env/prod/terraform.tfvars",
						"matched_alias": "payments-service",
						"matched_value": "payments-service",
						"extractor":     "terraform",
					},
				},
			},
		},
		EdgeWriter: edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v, want nil", err)
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
	if got, want := stringValue(row.Payload["relationship_type"]), string(relationships.RelProvisionsDependencyFor); got != want {
		t.Fatalf("relationship_type = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["repo_id"]), "repo-live"; got != want {
		t.Fatalf("repo_id = %q, want %q", got, want)
	}
	if got, want := stringValue(row.Payload["target_repo_id"]), "repo-payments"; got != want {
		t.Fatalf("target_repo_id = %q, want %q", got, want)
	}
}
