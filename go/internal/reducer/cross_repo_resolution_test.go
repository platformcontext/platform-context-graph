package reducer

import (
	"context"
	"fmt"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

// --- Test doubles ---

type fakeEvidenceFactLoader struct {
	facts []relationships.EvidenceFact
	err   error
}

func (f *fakeEvidenceFactLoader) ListEvidenceFacts(_ context.Context, _ string) ([]relationships.EvidenceFact, error) {
	return f.facts, f.err
}

type fakeAssertionLoader struct {
	assertions []relationships.Assertion
	err        error
}

func (f *fakeAssertionLoader) ListAssertions(_ context.Context, _ *relationships.RelationshipType) ([]relationships.Assertion, error) {
	return f.assertions, f.err
}

type fakeResolutionPersister struct {
	candidates []relationships.Candidate
	resolved   []relationships.ResolvedRelationship
}

func (f *fakeResolutionPersister) UpsertCandidates(_ context.Context, _ string, candidates []relationships.Candidate) error {
	f.candidates = append(f.candidates, candidates...)
	return nil
}

func (f *fakeResolutionPersister) UpsertResolved(_ context.Context, _ string, resolved []relationships.ResolvedRelationship) error {
	f.resolved = append(f.resolved, resolved...)
	return nil
}

type recordingEdgeWriter struct {
	writeCalls   []edgeWriteCall
	retractCalls []edgeRetractCall
}

type edgeWriteCall struct {
	domain         string
	rows           []SharedProjectionIntentRow
	evidenceSource string
}

type edgeRetractCall struct {
	domain         string
	rows           []SharedProjectionIntentRow
	evidenceSource string
}

func (r *recordingEdgeWriter) WriteEdges(_ context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	r.writeCalls = append(r.writeCalls, edgeWriteCall{
		domain:         domain,
		rows:           rows,
		evidenceSource: evidenceSource,
	})
	return nil
}

func (r *recordingEdgeWriter) RetractEdges(_ context.Context, domain string, rows []SharedProjectionIntentRow, evidenceSource string) error {
	r.retractCalls = append(r.retractCalls, edgeRetractCall{
		domain:         domain,
		rows:           rows,
		evidenceSource: evidenceSource,
	})
	return nil
}

// --- Tests ---

func TestCrossRepoResolutionSkipsWhenNoEvidence(t *testing.T) {
	t.Parallel()

	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: nil},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0", count)
	}
	if len(edgeWriter.writeCalls) != 0 {
		t.Fatalf("expected 0 write calls, got %d", len(edgeWriter.writeCalls))
	}
}

func TestCrossRepoResolutionSkipsWhenNilLoader(t *testing.T) {
	t.Parallel()

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: nil,
		EdgeWriter:     &recordingEdgeWriter{},
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0", count)
	}
}

func TestCrossRepoResolutionSkipsWhenNilEdgeWriter(t *testing.T) {
	t.Parallel()

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{
			facts: []relationships.EvidenceFact{
				{
					EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
					RelationshipType: relationships.RelProvisionsDependencyFor,
					SourceRepoID:     "infra-repo",
					TargetRepoID:     "app-repo",
					Confidence:       0.99,
				},
			},
		},
		EdgeWriter: nil,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0", count)
	}
}

func TestCrossRepoResolutionPropagatesEvidenceLoaderError(t *testing.T) {
	t.Parallel()

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{err: fmt.Errorf("db timeout")},
		EdgeWriter:     &recordingEdgeWriter{},
	}

	_, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err == nil {
		t.Fatal("Resolve() error = nil, want non-nil")
	}
}

func TestCrossRepoResolutionWritesDependencyEdges(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
			Rationale:        "Terraform app_repo points at the target repository",
		},
	}

	edgeWriter := &recordingEdgeWriter{}
	persister := &fakeResolutionPersister{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     edgeWriter,
		Persister:      persister,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1", count)
	}

	// Verify retraction happened first.
	if len(edgeWriter.retractCalls) != 1 {
		t.Fatalf("expected 1 retract call, got %d", len(edgeWriter.retractCalls))
	}
	if edgeWriter.retractCalls[0].domain != DomainRepoDependency {
		t.Fatalf("retract domain = %q, want %q", edgeWriter.retractCalls[0].domain, DomainRepoDependency)
	}

	// Verify write call.
	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("expected 1 write call, got %d", len(edgeWriter.writeCalls))
	}
	if edgeWriter.writeCalls[0].domain != DomainRepoDependency {
		t.Fatalf("write domain = %q, want %q", edgeWriter.writeCalls[0].domain, DomainRepoDependency)
	}
	if len(edgeWriter.writeCalls[0].rows) != 1 {
		t.Fatalf("expected 1 write row, got %d", len(edgeWriter.writeCalls[0].rows))
	}

	row := edgeWriter.writeCalls[0].rows[0]
	if got := row.Payload["repo_id"]; got != "infra-repo" {
		t.Fatalf("row repo_id = %v, want infra-repo", got)
	}
	if got := row.Payload["target_repo_id"]; got != "app-repo" {
		t.Fatalf("row target_repo_id = %v, want app-repo", got)
	}
}

func TestCrossRepoResolutionPersistsAuditTrail(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
			Rationale:        "Terraform app_repo points at target",
		},
	}

	persister := &fakeResolutionPersister{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     &recordingEdgeWriter{},
		Persister:      persister,
	}

	_, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}

	if len(persister.candidates) == 0 {
		t.Fatal("expected candidates to be persisted")
	}
	if len(persister.resolved) == 0 {
		t.Fatal("expected resolved relationships to be persisted")
	}
}

func TestCrossRepoResolutionRespectsAssertionRejections(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
			Rationale:        "Terraform app_repo points at target",
		},
	}

	assertions := []relationships.Assertion{
		{
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			RelationshipType: relationships.RelProvisionsDependencyFor,
			Decision:         "reject",
			Reason:           "false positive",
			Actor:            "admin",
		},
	}

	edgeWriter := &recordingEdgeWriter{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		Assertions:     &fakeAssertionLoader{assertions: assertions},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0 (rejected by assertion)", count)
	}
}

func TestCrossRepoResolutionFiltersLowConfidence(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformConfigPath,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.50, // below threshold
			Rationale:        "low confidence match",
		},
	}

	edgeWriter := &recordingEdgeWriter{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0 (below confidence threshold)", count)
	}
}

func TestCrossRepoResolutionMultipleRelationshipTypes(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo-1",
			Confidence:       0.99,
			Rationale:        "terraform app_repo",
		},
		{
			EvidenceKind:     relationships.EvidenceKindHelmChart,
			RelationshipType: relationships.RelDeploysFrom,
			SourceRepoID:     "deploy-repo",
			TargetRepoID:     "app-repo-2",
			Confidence:       0.90,
			Rationale:        "helm chart reference",
		},
	}

	edgeWriter := &recordingEdgeWriter{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 2 {
		t.Fatalf("Resolve() = %d, want 2", count)
	}

	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("expected 1 write call, got %d", len(edgeWriter.writeCalls))
	}
	if len(edgeWriter.writeCalls[0].rows) != 2 {
		t.Fatalf("expected 2 write rows, got %d", len(edgeWriter.writeCalls[0].rows))
	}
}

func TestCrossRepoResolutionDeduplicatesEvidence(t *testing.T) {
	t.Parallel()

	// Same evidence duplicated — should produce only 1 resolved edge.
	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
			Rationale:        "Terraform app_repo points at target",
		},
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "infra-repo",
			TargetRepoID:     "app-repo",
			Confidence:       0.99,
			Rationale:        "Terraform app_repo points at target",
		},
	}

	edgeWriter := &recordingEdgeWriter{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1 (deduped)", count)
	}
}
