package reducer

import (
	"context"
	"testing"
	"time"
)

func TestRunInlineSharedFollowupDrainsAllDomains(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	// Two pending intents across two domains, each in partition 0.
	pendingIntents := map[string][]SharedProjectionIntentRow{
		DomainPlatformInfra: {
			{
				IntentID:         "si-1",
				ProjectionDomain: DomainPlatformInfra,
				PartitionKey:     "pk-0",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{},
				CreatedAt:        now,
			},
		},
		DomainRepoDependency: {
			{
				IntentID:         "si-2",
				ProjectionDomain: DomainRepoDependency,
				PartitionKey:     "pk-0",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{},
				CreatedAt:        now,
			},
		},
	}

	lister := &fakeRepoRunIntentLister{pending: pendingIntents, drain: true}
	counter := &fakePendingGenerationCounter{counts: map[string]int{
		// After processing, count returns 0.
		DomainPlatformInfra:  0,
		DomainRepoDependency: 0,
	}}
	leaseManager := &fakeInlineLeaseManager{granted: true}
	reader := &fakeInlineIntentReader{pending: pendingIntents, drain: true}
	edgeWriter := &fakeInlineEdgeWriter{}

	remaining := RunInlineSharedFollowup(
		context.Background(),
		InlineFollowupConfig{
			RepositoryID:         "repo-a",
			SourceRunID:          "run-1",
			AcceptedGenerationID: "gen-1",
			AuthoritativeDomains: []string{DomainPlatformInfra, DomainRepoDependency},
			PartitionCount:       4,
			LeaseOwner:           "inline-test",
			LeaseTTL:             30 * time.Second,
			BatchLimit:           100,
		},
		lister,
		counter,
		leaseManager,
		reader,
		edgeWriter,
	)

	if len(remaining) != 0 {
		t.Fatalf("remaining = %v, want empty (all domains drained)", remaining)
	}
	if leaseManager.claims == 0 {
		t.Fatal("expected at least one lease claim")
	}
}

func TestRunInlineSharedFollowupReturnsStuckDomains(t *testing.T) {
	t.Parallel()

	now := time.Now().UTC()
	pendingIntents := map[string][]SharedProjectionIntentRow{
		DomainPlatformInfra: {
			{
				IntentID:         "si-stuck",
				ProjectionDomain: DomainPlatformInfra,
				PartitionKey:     "pk-0",
				RepositoryID:     "repo-a",
				SourceRunID:      "run-1",
				GenerationID:     "gen-1",
				Payload:          map[string]any{},
				CreatedAt:        now,
			},
		},
	}

	lister := &fakeRepoRunIntentLister{pending: pendingIntents}
	// Counter always returns 5 — the count never decreases, so it's stuck.
	counter := &fakePendingGenerationCounter{counts: map[string]int{
		DomainPlatformInfra: 5,
	}}
	leaseManager := &fakeInlineLeaseManager{granted: true}
	reader := &fakeInlineIntentReader{pending: pendingIntents}
	edgeWriter := &fakeInlineEdgeWriter{}

	remaining := RunInlineSharedFollowup(
		context.Background(),
		InlineFollowupConfig{
			RepositoryID:         "repo-a",
			SourceRunID:          "run-1",
			AcceptedGenerationID: "gen-1",
			AuthoritativeDomains: []string{DomainPlatformInfra},
			PartitionCount:       4,
			LeaseOwner:           "inline-test",
			LeaseTTL:             30 * time.Second,
			BatchLimit:           100,
		},
		lister,
		counter,
		leaseManager,
		reader,
		edgeWriter,
	)

	if len(remaining) != 1 || remaining[0] != DomainPlatformInfra {
		t.Fatalf("remaining = %v, want [%s]", remaining, DomainPlatformInfra)
	}
}

func TestRunInlineSharedFollowupEmptyDomainsReturnsNil(t *testing.T) {
	t.Parallel()

	remaining := RunInlineSharedFollowup(
		context.Background(),
		InlineFollowupConfig{
			RepositoryID:         "repo-a",
			SourceRunID:          "run-1",
			AcceptedGenerationID: "gen-1",
			AuthoritativeDomains: nil,
			PartitionCount:       4,
		},
		nil, nil, nil, nil, nil,
	)

	if remaining != nil {
		t.Fatalf("remaining = %v, want nil for empty domains", remaining)
	}
}

func TestRunInlineSharedFollowupEmptyGenerationReturnsNil(t *testing.T) {
	t.Parallel()

	remaining := RunInlineSharedFollowup(
		context.Background(),
		InlineFollowupConfig{
			RepositoryID:         "repo-a",
			SourceRunID:          "run-1",
			AcceptedGenerationID: "",
			AuthoritativeDomains: []string{DomainPlatformInfra},
			PartitionCount:       4,
		},
		nil, nil, nil, nil, nil,
	)

	if remaining != nil {
		t.Fatalf("remaining = %v, want nil for empty generation", remaining)
	}
}

func TestRunInlineSharedFollowupNoPendingIntentsSkipsDomain(t *testing.T) {
	t.Parallel()

	// Lister returns no pending intents for the domain.
	lister := &fakeRepoRunIntentLister{pending: map[string][]SharedProjectionIntentRow{}}
	counter := &fakePendingGenerationCounter{counts: map[string]int{}}

	remaining := RunInlineSharedFollowup(
		context.Background(),
		InlineFollowupConfig{
			RepositoryID:         "repo-a",
			SourceRunID:          "run-1",
			AcceptedGenerationID: "gen-1",
			AuthoritativeDomains: []string{DomainPlatformInfra, DomainRepoDependency},
			PartitionCount:       4,
			LeaseOwner:           "inline-test",
			LeaseTTL:             30 * time.Second,
			BatchLimit:           100,
		},
		lister,
		counter,
		nil, nil, nil,
	)

	if len(remaining) != 0 {
		t.Fatalf("remaining = %v, want empty (no pending intents)", remaining)
	}
}

// -- test fakes --

type fakeRepoRunIntentLister struct {
	pending map[string][]SharedProjectionIntentRow
	// drain controls whether pending intents are cleared after the first call.
	drain bool
}

func (f *fakeRepoRunIntentLister) ListPendingRepoRunIntents(_ context.Context, _, _ string, domain string, _ int) ([]SharedProjectionIntentRow, error) {
	rows := f.pending[domain]
	if f.drain {
		delete(f.pending, domain)
	}
	return rows, nil
}

type fakePendingGenerationCounter struct {
	counts map[string]int
}

func (f *fakePendingGenerationCounter) CountPendingGenerationIntents(_ context.Context, _, _, _ string, domain string) (int, error) {
	return f.counts[domain], nil
}

type fakeInlineLeaseManager struct {
	granted bool
	claims  int
}

func (f *fakeInlineLeaseManager) ClaimPartitionLease(context.Context, string, int, int, string, time.Duration) (bool, error) {
	f.claims++
	return f.granted, nil
}

func (f *fakeInlineLeaseManager) ReleasePartitionLease(context.Context, string, int, int, string) error {
	return nil
}

type fakeInlineIntentReader struct {
	pending   map[string][]SharedProjectionIntentRow
	drain     bool
	markCalls int
}

func (f *fakeInlineIntentReader) ListPendingDomainIntents(_ context.Context, domain string, _ int) ([]SharedProjectionIntentRow, error) {
	rows := f.pending[domain]
	if f.drain {
		delete(f.pending, domain)
	}
	return rows, nil
}

func (f *fakeInlineIntentReader) MarkIntentsCompleted(_ context.Context, _ []string, _ time.Time) error {
	f.markCalls++
	return nil
}

type fakeInlineEdgeWriter struct {
	retractCalls int
	writeCalls   int
}

func (f *fakeInlineEdgeWriter) RetractEdges(context.Context, string, []SharedProjectionIntentRow, string) error {
	f.retractCalls++
	return nil
}

func (f *fakeInlineEdgeWriter) WriteEdges(context.Context, string, []SharedProjectionIntentRow, string) error {
	f.writeCalls++
	return nil
}
