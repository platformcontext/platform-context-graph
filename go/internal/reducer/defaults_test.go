package reducer

import (
	"context"
	"testing"
	"time"
)

func TestNewDefaultRuntimeUsesDefaultDomainHandlers(t *testing.T) {
	t.Parallel()

	runtime, err := NewDefaultRuntime(DefaultHandlers{
		WorkloadIdentityWriter: &recordingWorkloadIdentityWriter{
			result: WorkloadIdentityWriteResult{
				CanonicalWrites: 1,
			},
		},
	})
	if err != nil {
		t.Fatalf("NewDefaultRuntime() error = %v, want nil", err)
	}

	workloadResult, err := runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "shared identity follow-up required",
		EntityKeys:      []string{"workload:platform-context-graph"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err != nil {
		t.Fatalf("runtime.Execute(workload) error = %v, want nil", err)
	}
	if got, want := workloadResult.Status, ResultStatusSucceeded; got != want {
		t.Fatalf("runtime.Execute(workload).Status = %q, want %q", got, want)
	}

	_, err = runtime.Execute(context.Background(), Intent{
		IntentID:        "intent-2",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainGovernance,
		Cause:           "shared governance follow-up required",
		EntityKeys:      []string{"policy:default"},
		RelatedScopeIDs: []string{"scope-123"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		Status:          IntentStatusClaimed,
	})
	if err == nil {
		t.Fatal("runtime.Execute(governance) error = nil, want non-nil")
	}
	if got, want := err.Error(), `domain "governance" is not registered`; got != want {
		t.Fatalf("runtime.Execute(governance) error = %q, want %q", got, want)
	}
}
