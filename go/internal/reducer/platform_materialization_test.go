package reducer

import (
	"context"
	"slices"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/relationships"
)

func TestPlatformMaterializationHandlerBuildsCanonicalWriteRequest(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{
		result: PlatformMaterializationWriteResult{
			CanonicalID:     "platform:kubernetes:aws:prod-cluster:production:us-east-1",
			CanonicalWrites: 2,
			EvidenceSummary: "materialized platform binding for prod-cluster",
		},
	}
	handler := PlatformMaterializationHandler{Writer: writer}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:     "intent-pm-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		SourceSystem: "git",
		Domain:       DomainDeploymentMapping,
		Cause:        "platform binding discovered",
		EntityKeys: []string{
			"platform:kubernetes:aws:prod-cluster:production:us-east-1",
			"repo:infra-eks",
			"platform:kubernetes:aws:prod-cluster:production:us-east-1",
		},
		RelatedScopeIDs: []string{
			"scope-999",
			"scope-123",
			"scope-999",
		},
		EnqueuedAt:  time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt: time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:      IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}

	if got, want := len(writer.requests), 1; got != want {
		t.Fatalf("writer request count = %d, want %d", got, want)
	}

	request := writer.requests[0]
	if got, want := request.IntentID, "intent-pm-1"; got != want {
		t.Fatalf("request.IntentID = %q, want %q", got, want)
	}
	if got, want := request.ScopeID, "scope-123"; got != want {
		t.Fatalf("request.ScopeID = %q, want %q", got, want)
	}
	if got, want := request.GenerationID, "generation-456"; got != want {
		t.Fatalf("request.GenerationID = %q, want %q", got, want)
	}
	if got, want := request.SourceSystem, "git"; got != want {
		t.Fatalf("request.SourceSystem = %q, want %q", got, want)
	}
	if got, want := request.Cause, "platform binding discovered"; got != want {
		t.Fatalf("request.Cause = %q, want %q", got, want)
	}

	wantEntityKeys := []string{
		"platform:kubernetes:aws:prod-cluster:production:us-east-1",
		"repo:infra-eks",
	}
	if !slices.Equal(request.EntityKeys, wantEntityKeys) {
		t.Fatalf("request.EntityKeys = %v, want %v", request.EntityKeys, wantEntityKeys)
	}

	wantRelatedScopes := []string{
		"scope-123",
		"scope-999",
	}
	if !slices.Equal(request.RelatedScopeIDs, wantRelatedScopes) {
		t.Fatalf("request.RelatedScopeIDs = %v, want %v", request.RelatedScopeIDs, wantRelatedScopes)
	}

	if got, want := result.IntentID, "intent-pm-1"; got != want {
		t.Fatalf("result.IntentID = %q, want %q", got, want)
	}
	if got, want := result.Domain, DomainDeploymentMapping; got != want {
		t.Fatalf("result.Domain = %q, want %q", got, want)
	}
	if got, want := result.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("result.Status = %q, want %q", got, want)
	}
	if got, want := result.CanonicalWrites, 2; got != want {
		t.Fatalf("result.CanonicalWrites = %d, want %d", got, want)
	}
	if got, want := result.EvidenceSummary, "materialized platform binding for prod-cluster"; got != want {
		t.Fatalf("result.EvidenceSummary = %q, want %q", got, want)
	}
}

func TestPlatformMaterializationHandlerDefaultEvidenceSummary(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{
		result: PlatformMaterializationWriteResult{
			CanonicalWrites: 1,
		},
	}
	handler := PlatformMaterializationHandler{Writer: writer}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-pm-2",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform discovered",
		EntityKeys:      []string{"platform:ecs:aws:payments-cluster"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}

	wantSummary := "materialized 1 platform key(s) across 1 scope(s)"
	if got := result.EvidenceSummary; got != wantSummary {
		t.Fatalf("result.EvidenceSummary = %q, want %q", got, wantSummary)
	}
}

func TestPlatformMaterializationHandlerRejectsMissingEntityKeys(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{}
	handler := PlatformMaterializationHandler{Writer: writer}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-pm-3",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform binding discovered",
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
	if got, want := len(writer.requests), 0; got != want {
		t.Fatalf("writer request count = %d, want %d", got, want)
	}
}

func TestPlatformMaterializationHandlerRequiresCanonicalWriter(t *testing.T) {
	t.Parallel()

	handler := PlatformMaterializationHandler{}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-pm-4",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform binding discovered",
		EntityKeys:      []string{"platform:kubernetes:aws:prod-cluster"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
	if got, want := err.Error(), "platform materialization writer is required"; got != want {
		t.Fatalf("Handle() error = %q, want %q", got, want)
	}
}

func TestPlatformMaterializationHandlerRejectsMismatchedDomain(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{}
	handler := PlatformMaterializationHandler{Writer: writer}

	_, err := handler.Handle(context.Background(), Intent{
		IntentID: "intent-pm-5",
		Domain:   DomainWorkloadIdentity,
	})
	if err == nil {
		t.Fatal("Handle() error = nil, want non-nil")
	}
}

func TestPlatformMaterializationHandlerCallsCrossRepoResolver(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{
		result: PlatformMaterializationWriteResult{
			CanonicalWrites: 1,
		},
	}

	edgeWriter := &recordingEdgeWriter{}
	handler := PlatformMaterializationHandler{
		Writer: writer,
		CrossRepoResolver: &CrossRepoRelationshipHandler{
			EvidenceLoader: &fakeEvidenceFactLoader{
				facts: []relationships.EvidenceFact{
					{
						EvidenceKind:     relationships.EvidenceKindTerraformAppRepo,
						RelationshipType: relationships.RelProvisionsDependencyFor,
						SourceRepoID:     "infra-repo",
						TargetRepoID:     "app-repo",
						Confidence:       0.99,
						Rationale:        "Terraform app_repo reference",
					},
				},
			},
			EdgeWriter: edgeWriter,
		},
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-pm-cross",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform discovered",
		EntityKeys:      []string{"platform:kubernetes:aws:prod-cluster"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}

	// Platform write (1) + cross-repo edge write (1) = 2 total.
	if got, want := result.CanonicalWrites, 2; got != want {
		t.Fatalf("result.CanonicalWrites = %d, want %d", got, want)
	}

	if len(edgeWriter.writeCalls) != 1 {
		t.Fatalf("expected 1 edge write call, got %d", len(edgeWriter.writeCalls))
	}
	if edgeWriter.writeCalls[0].domain != DomainRepoDependency {
		t.Fatalf("edge write domain = %q, want %q", edgeWriter.writeCalls[0].domain, DomainRepoDependency)
	}
}

func TestPlatformMaterializationHandlerSkipsCrossRepoWhenNilResolver(t *testing.T) {
	t.Parallel()

	writer := &recordingPlatformMaterializationWriter{
		result: PlatformMaterializationWriteResult{CanonicalWrites: 1},
	}
	handler := PlatformMaterializationHandler{
		Writer:            writer,
		CrossRepoResolver: nil,
	}

	result, err := handler.Handle(context.Background(), Intent{
		IntentID:        "intent-pm-no-cross",
		ScopeID:         "scope-1",
		GenerationID:    "gen-1",
		SourceSystem:    "git",
		Domain:          DomainDeploymentMapping,
		Cause:           "platform discovered",
		EntityKeys:      []string{"platform:ecs:aws:cluster"},
		RelatedScopeIDs: []string{"scope-1"},
		EnqueuedAt:      time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("Handle() error = %v, want nil", err)
	}
	if got, want := result.CanonicalWrites, 1; got != want {
		t.Fatalf("result.CanonicalWrites = %d, want %d", got, want)
	}
}

type recordingPlatformMaterializationWriter struct {
	requests []PlatformMaterializationWrite
	result   PlatformMaterializationWriteResult
	err      error
}

func (w *recordingPlatformMaterializationWriter) WritePlatformMaterialization(
	_ context.Context,
	request PlatformMaterializationWrite,
) (PlatformMaterializationWriteResult, error) {
	w.requests = append(w.requests, request)
	return w.result, w.err
}
