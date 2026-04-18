package reducer

import (
	"bytes"
	"context"
	"fmt"
	"log/slog"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

// --- Test doubles ---

type fakeEvidenceFactLoader struct {
	facts []relationships.EvidenceFact
	err   error
	calls int
}

func (f *fakeEvidenceFactLoader) ListEvidenceFacts(_ context.Context, _ string) ([]relationships.EvidenceFact, error) {
	f.calls++
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

func TestCrossRepoResolutionGatesUntilBackwardEvidenceCommitted(t *testing.T) {
	t.Parallel()

	evidenceLoader := &fakeEvidenceFactLoader{
		facts: []relationships.EvidenceFact{
			{
				EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
				RelationshipType: relationships.RelProvisionsDependencyFor,
				SourceRepoID:     "infra-repo",
				TargetRepoID:     "app-repo",
				Confidence:       0.99,
			},
		},
	}
	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: evidenceLoader,
		EdgeWriter:     edgeWriter,
		ReadinessLookup: func(key GraphProjectionPhaseKey, phase GraphProjectionPhase) (bool, bool) {
			if got, want := key.ScopeID, "scope-1"; got != want {
				t.Fatalf("ScopeID = %q, want %q", got, want)
			}
			if got, want := key.AcceptanceUnitID, "scope-1"; got != want {
				t.Fatalf("AcceptanceUnitID = %q, want %q", got, want)
			}
			if got, want := key.SourceRunID, "gen-1"; got != want {
				t.Fatalf("SourceRunID = %q, want %q", got, want)
			}
			if got, want := key.GenerationID, "gen-1"; got != want {
				t.Fatalf("GenerationID = %q, want %q", got, want)
			}
			if got, want := key.Keyspace, GraphProjectionKeyspaceCrossRepoEvidence; got != want {
				t.Fatalf("Keyspace = %q, want %q", got, want)
			}
			if got, want := phase, GraphProjectionPhaseBackwardEvidenceCommitted; got != want {
				t.Fatalf("phase = %q, want %q", got, want)
			}
			return false, false
		},
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 0 {
		t.Fatalf("Resolve() = %d, want 0 when readiness is missing", count)
	}
	if evidenceLoader.calls != 0 {
		t.Fatalf("evidence loader calls = %d, want 0 when gated", evidenceLoader.calls)
	}
	if len(edgeWriter.retractCalls) != 0 {
		t.Fatalf("retractCalls = %d, want 0 when gated", len(edgeWriter.retractCalls))
	}
	if len(edgeWriter.writeCalls) != 0 {
		t.Fatalf("writeCalls = %d, want 0 when gated", len(edgeWriter.writeCalls))
	}
}

func TestCrossRepoResolutionUsesReadinessPrefetchWhenAvailable(t *testing.T) {
	t.Parallel()

	evidenceLoader := &fakeEvidenceFactLoader{
		facts: []relationships.EvidenceFact{
			{
				EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
				RelationshipType: relationships.RelProvisionsDependencyFor,
				SourceRepoID:     "infra-repo",
				TargetRepoID:     "app-repo",
				Confidence:       0.99,
			},
		},
	}
	edgeWriter := &recordingEdgeWriter{}
	prefetchCalls := 0
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: evidenceLoader,
		EdgeWriter:     edgeWriter,
		ReadinessLookup: func(GraphProjectionPhaseKey, GraphProjectionPhase) (bool, bool) {
			t.Fatal("ReadinessLookup should be replaced by prefetched lookup")
			return false, false
		},
		ReadinessPrefetch: func(_ context.Context, keys []GraphProjectionPhaseKey, phase GraphProjectionPhase) (GraphProjectionReadinessLookup, error) {
			prefetchCalls++
			if got, want := phase, GraphProjectionPhaseBackwardEvidenceCommitted; got != want {
				t.Fatalf("phase = %q, want %q", got, want)
			}
			if len(keys) != 1 {
				t.Fatalf("prefetch keys = %d, want 1", len(keys))
			}
			key := keys[0]
			if got, want := key.ScopeID, "scope-1"; got != want {
				t.Fatalf("ScopeID = %q, want %q", got, want)
			}
			if got, want := key.AcceptanceUnitID, "scope-1"; got != want {
				t.Fatalf("AcceptanceUnitID = %q, want %q", got, want)
			}
			if got, want := key.SourceRunID, "gen-1"; got != want {
				t.Fatalf("SourceRunID = %q, want %q", got, want)
			}
			if got, want := key.GenerationID, "gen-1"; got != want {
				t.Fatalf("GenerationID = %q, want %q", got, want)
			}
			if got, want := key.Keyspace, GraphProjectionKeyspaceCrossRepoEvidence; got != want {
				t.Fatalf("Keyspace = %q, want %q", got, want)
			}
			return func(lookupKey GraphProjectionPhaseKey, lookupPhase GraphProjectionPhase) (bool, bool) {
				if lookupKey != key {
					t.Fatalf("lookup key = %#v, want %#v", lookupKey, key)
				}
				if lookupPhase != phase {
					t.Fatalf("lookup phase = %q, want %q", lookupPhase, phase)
				}
				return true, true
			}, nil
		},
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1 when readiness is committed", count)
	}
	if prefetchCalls != 1 {
		t.Fatalf("prefetch calls = %d, want 1", prefetchCalls)
	}
	if evidenceLoader.calls != 1 {
		t.Fatalf("evidence loader calls = %d, want 1 after readiness", evidenceLoader.calls)
	}
	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("writeCalls = %d, want 1", len(edgeWriter.writeCalls))
	}
}

func TestCrossRepoResolutionWarnsWhenReadinessGateBypassed(t *testing.T) {
	var logs bytes.Buffer
	previous := slog.Default()
	slog.SetDefault(slog.New(slog.NewTextHandler(&logs, &slog.HandlerOptions{Level: slog.LevelWarn})))
	defer slog.SetDefault(previous)

	evidenceLoader := &fakeEvidenceFactLoader{
		facts: []relationships.EvidenceFact{
			{
				EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
				RelationshipType: relationships.RelProvisionsDependencyFor,
				SourceRepoID:     "infra-repo",
				TargetRepoID:     "app-repo",
				Confidence:       0.99,
			},
		},
	}
	edgeWriter := &recordingEdgeWriter{}
	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: evidenceLoader,
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-1", "gen-1")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 1 {
		t.Fatalf("Resolve() = %d, want 1 when gate wiring is absent", count)
	}
	if !bytes.Contains(logs.Bytes(), []byte("cross-repo readiness lookup not configured")) {
		t.Fatalf("warning log = %q, want missing readiness warning", logs.String())
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
	if got, want := row.Payload["evidence_type"], "terraform_app_repo"; got != want {
		t.Fatalf("row evidence_type = %v, want %q", got, want)
	}
}

func TestCrossRepoResolutionNormalizesScopedRepositoryIDs(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
			RelationshipType: relationships.RelProvisionsDependencyFor,
			SourceRepoID:     "git-repository-scope:repository:r_infra",
			TargetRepoID:     "repository:r_app",
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
	if len(edgeWriter.retractCalls) != 1 || len(edgeWriter.retractCalls[0].rows) != 1 {
		t.Fatalf("unexpected retract calls: %#v", edgeWriter.retractCalls)
	}
	if got, want := edgeWriter.retractCalls[0].rows[0].RepositoryID, "repository:r_infra"; got != want {
		t.Fatalf("retract repository_id = %q, want %q", got, want)
	}
	if len(edgeWriter.writeCalls) != 1 || len(edgeWriter.writeCalls[0].rows) != 1 {
		t.Fatalf("unexpected write calls: %#v", edgeWriter.writeCalls)
	}
	if got, want := edgeWriter.writeCalls[0].rows[0].Payload["repo_id"], "repository:r_infra"; got != want {
		t.Fatalf("write repo_id = %v, want %q", got, want)
	}
	if got, want := edgeWriter.writeCalls[0].rows[0].Payload["target_repo_id"], "repository:r_app"; got != want {
		t.Fatalf("write target_repo_id = %v, want %q", got, want)
	}
	if len(persister.resolved) != 1 {
		t.Fatalf("persisted resolved = %d, want 1", len(persister.resolved))
	}
	if got, want := persister.resolved[0].SourceRepoID, "repository:r_infra"; got != want {
		t.Fatalf("persisted source repo = %q, want %q", got, want)
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

func TestCrossRepoResolutionPreservesGitHubActionsTypedRelationships(t *testing.T) {
	t.Parallel()

	evidence := []relationships.EvidenceFact{
		{
			EvidenceKind:     relationships.EvidenceKindGitHubActionsReusableWorkflow,
			RelationshipType: relationships.RelDeploysFrom,
			SourceRepoID:     "repo-service",
			TargetRepoID:     "repo-automation",
			Confidence:       0.93,
		},
		{
			EvidenceKind:     relationships.EvidenceKindGitHubActionsWorkflowInputRepository,
			RelationshipType: relationships.RelDiscoversConfigIn,
			SourceRepoID:     "repo-service",
			TargetRepoID:     "repo-automation",
			Confidence:       0.90,
		},
	}

	edgeWriter := &recordingEdgeWriter{}

	handler := CrossRepoRelationshipHandler{
		EvidenceLoader: &fakeEvidenceFactLoader{facts: evidence},
		EdgeWriter:     edgeWriter,
	}

	count, err := handler.Resolve(context.Background(), "scope-gha", "gen-gha")
	if err != nil {
		t.Fatalf("Resolve() error = %v", err)
	}
	if count != 2 {
		t.Fatalf("Resolve() = %d, want 2", count)
	}

	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("expected 1 write call, got %d", len(edgeWriter.writeCalls))
	}
	rows := edgeWriter.writeCalls[0].rows
	if len(rows) != 2 {
		t.Fatalf("expected 2 write rows, got %d", len(rows))
	}

	gotTypes := map[string]struct{}{}
	for _, row := range rows {
		gotTypes[stringValue(row.Payload["relationship_type"])] = struct{}{}
		if got := stringValue(row.Payload["repo_id"]); got != "repo-service" {
			t.Fatalf("row repo_id = %q, want %q", got, "repo-service")
		}
		if got := stringValue(row.Payload["target_repo_id"]); got != "repo-automation" {
			t.Fatalf("row target_repo_id = %q, want %q", got, "repo-automation")
		}
	}
	for _, want := range []string{string(relationships.RelDeploysFrom), string(relationships.RelDiscoversConfigIn)} {
		if _, ok := gotTypes[want]; !ok {
			t.Fatalf("missing relationship_type %q in write rows", want)
		}
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
