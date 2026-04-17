package reducer

import (
	"context"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestCrossRepoResolutionPreservesControllerAndConfigEvidenceFamilies(t *testing.T) {
	t.Parallel()

	testCases := []struct {
		name             string
		evidenceKind     relationships.EvidenceKind
		relationshipType relationships.RelationshipType
		wantEvidenceType string
	}{
		{
			name:             "github actions action repository stays depends_on",
			evidenceKind:     relationships.EvidenceKindGitHubActionsActionRepository,
			relationshipType: relationships.RelDependsOn,
			wantEvidenceType: "github_actions_action_repository",
		},
		{
			name:             "jenkins shared library stays discovers_config_in",
			evidenceKind:     relationships.EvidenceKindJenkinsSharedLibrary,
			relationshipType: relationships.RelDiscoversConfigIn,
			wantEvidenceType: "jenkins_shared_library",
		},
		{
			name:             "jenkins github repository stays discovers_config_in",
			evidenceKind:     relationships.EvidenceKindJenkinsGitHubRepository,
			relationshipType: relationships.RelDiscoversConfigIn,
			wantEvidenceType: "jenkins_github_repository",
		},
		{
			name:             "ansible role reference stays depends_on",
			evidenceKind:     relationships.EvidenceKindAnsibleRoleReference,
			relationshipType: relationships.RelDependsOn,
			wantEvidenceType: "ansible_role_reference",
		},
		{
			name:             "terragrunt dependency config path stays discovers_config_in",
			evidenceKind:     relationships.EvidenceKindTerragruntDependencyConfigPath,
			relationshipType: relationships.RelDiscoversConfigIn,
			wantEvidenceType: "terragrunt_dependency_config_path",
		},
		{
			name:             "terragrunt config asset stays discovers_config_in",
			evidenceKind:     relationships.EvidenceKindTerragruntConfigAssetPath,
			relationshipType: relationships.RelDiscoversConfigIn,
			wantEvidenceType: "terragrunt_config_asset_path",
		},
	}

	for _, tc := range testCases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()

			edgeWriter := &recordingEdgeWriter{}
			handler := CrossRepoRelationshipHandler{
				EvidenceLoader: &fakeEvidenceFactLoader{facts: []relationships.EvidenceFact{
					{
						EvidenceKind:     tc.evidenceKind,
						RelationshipType: tc.relationshipType,
						SourceRepoID:     "repo-service",
						TargetRepoID:     "repo-target",
						Confidence:       0.92,
					},
				}},
				EdgeWriter: edgeWriter,
			}

			count, err := handler.Resolve(context.Background(), "scope-controller", "gen-controller")
			if err != nil {
				t.Fatalf("Resolve() error = %v", err)
			}
			if count != 1 {
				t.Fatalf("Resolve() = %d, want 1", count)
			}
			if len(edgeWriter.writeCalls) != 1 {
				t.Fatalf("expected 1 write call, got %d", len(edgeWriter.writeCalls))
			}
			if len(edgeWriter.writeCalls[0].rows) != 1 {
				t.Fatalf("expected 1 write row, got %d", len(edgeWriter.writeCalls[0].rows))
			}

			row := edgeWriter.writeCalls[0].rows[0]
			if got := stringValue(row.Payload["repo_id"]); got != "repo-service" {
				t.Fatalf("row repo_id = %q, want %q", got, "repo-service")
			}
			if got := stringValue(row.Payload["target_repo_id"]); got != "repo-target" {
				t.Fatalf("row target_repo_id = %q, want %q", got, "repo-target")
			}
			if got, want := stringValue(row.Payload["relationship_type"]), string(tc.relationshipType); got != want {
				t.Fatalf("row relationship_type = %q, want %q", got, want)
			}
			if got, want := stringValue(row.Payload["evidence_type"]), tc.wantEvidenceType; got != want {
				t.Fatalf("row evidence_type = %q, want %q", got, want)
			}
		})
	}
}
