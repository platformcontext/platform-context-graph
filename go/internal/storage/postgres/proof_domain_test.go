package postgres

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
)

func TestProofDomainWorkloadIdentityFlowsCollectorToReducerIntent(t *testing.T) {
	t.Parallel()

	now := time.Date(2026, time.April, 12, 12, 30, 0, 0, time.UTC)
	db := newProofDomainDB(t, now)

	scopeValue := scope.IngestionScope{
		ScopeID:       "scope-123",
		SourceSystem:  "git",
		ScopeKind:     scope.KindRepository,
		CollectorKind: scope.CollectorGit,
		PartitionKey:  "repo-123",
		Metadata: map[string]string{
			"repo_id":    "repo-123",
			"source_key": "repo-123",
		},
	}
	generation := scope.ScopeGeneration{
		GenerationID: "generation-456",
		ScopeID:      "scope-123",
		ObservedAt:   time.Date(2026, time.April, 12, 12, 0, 0, 0, time.UTC),
		IngestedAt:   now,
		Status:       scope.GenerationStatusPending,
		TriggerKind:  scope.TriggerKindSnapshot,
	}
	envelopes := []facts.Envelope{
		{
			FactID:        "fact-1",
			ScopeID:       "scope-123",
			GenerationID:  "generation-456",
			FactKind:      "repository",
			StableFactKey: "repository:repo-123",
			ObservedAt:    generation.ObservedAt,
			Payload: map[string]any{
				"graph_id":   "repo-123",
				"graph_kind": "repository",
				"name":       "platform-context-graph",
			},
			SourceRef: facts.Ref{
				SourceSystem: "git",
				FactKey:      "repo-123",
			},
		},
		{
			FactID:        "fact-2",
			ScopeID:       "scope-123",
			GenerationID:  "generation-456",
			FactKind:      "content",
			StableFactKey: "content:README.md",
			ObservedAt:    generation.ObservedAt,
			Payload: map[string]any{
				"content_path":   "README.md",
				"content_body":   "# Platform Context Graph\n",
				"content_digest": "digest-1",
			},
			SourceRef: facts.Ref{
				SourceSystem: "git",
				FactKey:      "README.md",
			},
		},
		{
			FactID:        "fact-3",
			ScopeID:       "scope-123",
			GenerationID:  "generation-456",
			FactKind:      "shared_follow_up",
			StableFactKey: "shared:workload_identity",
			ObservedAt:    generation.ObservedAt,
			Payload: map[string]any{
				"reducer_domain": "workload_identity",
				"entity_key":     "workload:platform-context-graph",
				"reason":         "repo snapshot emitted shared workload identity work",
				"fact_id":        "fact-3",
				"source_system":  "git",
			},
			SourceRef: facts.Ref{
				SourceSystem: "git",
				FactKey:      "workload_identity",
			},
		},
	}

	ingestionStore := NewIngestionStore(db)
	ingestionStore.Now = func() time.Time { return now }
	if err := ingestionStore.CommitScopeGeneration(context.Background(), scopeValue, generation, envelopes); err != nil {
		t.Fatalf("CommitScopeGeneration() error = %v, want nil", err)
	}

	projectorQueue := ProjectorQueue{
		db:            db,
		LeaseOwner:    "projector-1",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}
	factStore := NewFactStore(db)
	graphWriter := &recordingGraphWriter{}
	contentWriter := &recordingContentWriter{}
	reducerQueue := ReducerQueue{
		db:            db,
		LeaseOwner:    "reducer-1",
		LeaseDuration: time.Minute,
		Now:           func() time.Time { return now },
	}
	projectorRuntime := projector.Runtime{
		GraphWriter:   graphWriter,
		ContentWriter: contentWriter,
		IntentWriter:  reducerQueue,
	}
	projectorService := projector.Service{
		PollInterval: time.Millisecond,
		WorkSource:   projectorQueue,
		FactStore:    factStore,
		Runner:       projectorRuntime,
		WorkSink:     projectorQueue,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	if err := projectorService.Run(context.Background()); err != nil {
		t.Fatalf("projector service Run() error = %v, want nil", err)
	}

	reducerRegistry := reducer.NewRegistry()
	if err := reducerRegistry.Register(reducer.DomainDefinition{
		Domain:  reducer.DomainWorkloadIdentity,
		Summary: "resolve canonical workload identity across sources",
		Ownership: reducer.OwnershipShape{
			CrossSource:    true,
			CrossScope:     true,
			CanonicalWrite: true,
		},
		Handler: reducer.HandlerFunc(func(context.Context, reducer.Intent) (reducer.Result, error) {
			return reducer.Result{
				Status:          reducer.ResultStatusSucceeded,
				EvidenceSummary: "workload identity canonicalized",
				CanonicalWrites: 1,
				CompletedAt:     now,
			}, nil
		}),
	}); err != nil {
		t.Fatalf("Register() error = %v, want nil", err)
	}
	reducerRuntime, err := reducer.NewRuntime(reducerRegistry)
	if err != nil {
		t.Fatalf("NewRuntime() error = %v, want nil", err)
	}
	reducerService := reducer.Service{
		PollInterval: time.Millisecond,
		WorkSource:   reducerQueue,
		Executor:     reducerRuntime,
		WorkSink:     reducerQueue,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	if err := reducerService.Run(context.Background()); err != nil {
		t.Fatalf("reducer service Run() error = %v, want nil", err)
	}

	if got, want := len(graphWriter.calls), 1; got != want {
		t.Fatalf("graph writes = %d, want %d", got, want)
	}
	if got, want := len(contentWriter.calls), 1; got != want {
		t.Fatalf("content writes = %d, want %d", got, want)
	}
	if got, want := len(graphWriter.calls[0].Records), 1; got != want {
		t.Fatalf("graph record count = %d, want %d", got, want)
	}
	if got, want := len(contentWriter.calls[0].Records), 1; got != want {
		t.Fatalf("content record count = %d, want %d", got, want)
	}
	if got, want := db.reducerClaims, 1; got != want {
		t.Fatalf("reducer claims = %d, want %d", got, want)
	}
	if got, want := db.reducerAcked, 1; got != want {
		t.Fatalf("reducer acknowledgements = %d, want %d", got, want)
	}
}
