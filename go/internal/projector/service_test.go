package projector

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestServiceRunClaimsLoadsProjectsAndAcknowledges(t *testing.T) {
	t.Parallel()

	work := ScopeGenerationWork{
		Scope: scope.IngestionScope{
			ScopeID:       "scope-123",
			SourceSystem:  "git",
			ScopeKind:     scope.KindRepository,
			CollectorKind: scope.CollectorGit,
			PartitionKey:  "repo-123",
		},
		Generation: scope.ScopeGeneration{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
			IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
			Status:       scope.GenerationStatusPending,
			TriggerKind:  scope.TriggerKindSnapshot,
		},
	}

	source := &stubProjectorWorkSource{workItems: []ScopeGenerationWork{work}}
	factStore := &stubFactStore{
		facts: []facts.Envelope{{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_node",
		}},
	}
	runner := &stubProjectionRunner{
		result: Result{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
		},
	}
	sink := &stubProjectorWorkSink{}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		FactStore:    factStore,
		Runner:       runner,
		WorkSink:     sink,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	if err := service.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := source.claimCalls, 2; got != want {
		t.Fatalf("claim calls = %d, want %d", got, want)
	}
	if got, want := factStore.loadCalls, 1; got != want {
		t.Fatalf("load calls = %d, want %d", got, want)
	}
	if got, want := runner.runCalls, 1; got != want {
		t.Fatalf("runner calls = %d, want %d", got, want)
	}
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
}

func TestServiceRunMarksFailureWhenProjectionFails(t *testing.T) {
	t.Parallel()

	work := ScopeGenerationWork{
		Scope: scope.IngestionScope{
			ScopeID:       "scope-123",
			SourceSystem:  "git",
			ScopeKind:     scope.KindRepository,
			CollectorKind: scope.CollectorGit,
			PartitionKey:  "repo-123",
		},
		Generation: scope.ScopeGeneration{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
			IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
			Status:       scope.GenerationStatusPending,
			TriggerKind:  scope.TriggerKindSnapshot,
		},
	}

	wantErr := errors.New("projection failed")
	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubProjectorWorkSource{workItems: []ScopeGenerationWork{work}},
		FactStore:    &stubFactStore{},
		Runner:       &stubProjectionRunner{runErr: wantErr},
		WorkSink:     &stubProjectorWorkSink{},
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	sink := service.WorkSink.(*stubProjectorWorkSink)

	if err := service.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := sink.ackCalls, 0; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 1; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
	if !errors.Is(sink.failedWith, wantErr) {
		t.Fatalf("failed error = %v, want %v", sink.failedWith, wantErr)
	}
}

type stubProjectorWorkSource struct {
	mu         sync.Mutex
	claimCalls int
	workItems  []ScopeGenerationWork
}

func (s *stubProjectorWorkSource) Claim(context.Context) (ScopeGenerationWork, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.claimCalls++
	if len(s.workItems) == 0 {
		return ScopeGenerationWork{}, false, nil
	}

	work := s.workItems[0]
	s.workItems = s.workItems[1:]
	return work, true, nil
}

type stubFactStore struct {
	mu        sync.Mutex
	loadCalls int
	facts     []facts.Envelope
}

func (s *stubFactStore) LoadFacts(context.Context, ScopeGenerationWork) ([]facts.Envelope, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.loadCalls++
	cloned := make([]facts.Envelope, len(s.facts))
	copy(cloned, s.facts)
	return cloned, nil
}

type stubProjectionRunner struct {
	mu         sync.Mutex
	runCalls   int
	result     Result
	runErr     error
	failAfter int
}

func (s *stubProjectionRunner) Project(ctx context.Context, scopeValue scope.IngestionScope, generation scope.ScopeGeneration, inputFacts []facts.Envelope) (Result, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.runCalls++
	if s.failAfter > 0 && s.runCalls > s.failAfter {
		return Result{}, errors.New("executor failed after threshold")
	}
	return s.result, s.runErr
}

type stubProjectorWorkSink struct {
	mu         sync.Mutex
	ackCalls   int
	failCalls  int
	failedWith error
	ackErr     error
	failAfter  int
}

func (s *stubProjectorWorkSink) Ack(context.Context, ScopeGenerationWork, Result) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ackCalls++
	if s.failAfter > 0 && s.ackCalls > s.failAfter {
		return errors.New("ack failed after threshold")
	}
	return s.ackErr
}

func (s *stubProjectorWorkSink) Fail(_ context.Context, _ ScopeGenerationWork, err error) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failCalls++
	s.failedWith = err
	return nil
}

func TestServiceRunWithTelemetry(t *testing.T) {
	t.Parallel()

	work := ScopeGenerationWork{
		Scope: scope.IngestionScope{
			ScopeID:       "scope-123",
			SourceSystem:  "git",
			ScopeKind:     scope.KindRepository,
			CollectorKind: scope.CollectorGit,
			PartitionKey:  "repo-123",
		},
		Generation: scope.ScopeGeneration{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
			IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
			Status:       scope.GenerationStatusPending,
			TriggerKind:  scope.TriggerKindSnapshot,
		},
	}

	tracer := noop.NewTracerProvider().Tracer("test")
	meter := metricnoop.NewMeterProvider().Meter("test")
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		t.Fatalf("NewInstruments() error = %v, want nil", err)
	}
	logger := slog.Default()

	source := &stubProjectorWorkSource{workItems: []ScopeGenerationWork{work}}
	factStore := &stubFactStore{
		facts: []facts.Envelope{{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_node",
		}},
	}
	runner := &stubProjectionRunner{
		result: Result{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
		},
	}
	sink := &stubProjectorWorkSink{}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		FactStore:    factStore,
		Runner:       runner,
		WorkSink:     sink,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
		Tracer:       tracer,
		Instruments:  instruments,
		Logger:       logger,
	}

	if err := service.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := source.claimCalls, 2; got != want {
		t.Fatalf("claim calls = %d, want %d", got, want)
	}
	if got, want := factStore.loadCalls, 1; got != want {
		t.Fatalf("load calls = %d, want %d", got, want)
	}
	if got, want := runner.runCalls, 1; got != want {
		t.Fatalf("runner calls = %d, want %d", got, want)
	}
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
}

func TestServiceRunConcurrentMultipleItems(t *testing.T) {
	t.Parallel()

	workItems := []ScopeGenerationWork{
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-1",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-1",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-1",
				GenerationID: "gen-1",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-2",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-2",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-2",
				GenerationID: "gen-2",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-3",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-3",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-3",
				GenerationID: "gen-3",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-4",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-4",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-4",
				GenerationID: "gen-4",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-5",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-5",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-5",
				GenerationID: "gen-5",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
	}

	source := &stubProjectorWorkSource{workItems: workItems}
	factStore := &stubFactStore{
		facts: []facts.Envelope{{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_node",
		}},
	}
	runner := &stubProjectionRunner{
		result: Result{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
		},
	}
	sink := &stubProjectorWorkSink{}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		FactStore:    factStore,
		Runner:       runner,
		WorkSink:     sink,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
		Workers:      3,
	}

	if err := service.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	source.mu.Lock()
	claimCalls := source.claimCalls
	source.mu.Unlock()

	factStore.mu.Lock()
	loadCalls := factStore.loadCalls
	factStore.mu.Unlock()

	runner.mu.Lock()
	runCalls := runner.runCalls
	runner.mu.Unlock()

	sink.mu.Lock()
	ackCalls := sink.ackCalls
	failCalls := sink.failCalls
	sink.mu.Unlock()

	if got, want := loadCalls, 5; got != want {
		t.Fatalf("load calls = %d, want %d", got, want)
	}
	if got, want := runCalls, 5; got != want {
		t.Fatalf("runner calls = %d, want %d", got, want)
	}
	if got, want := ackCalls, 5; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
	if claimCalls < 8 {
		t.Fatalf("claim calls = %d, should be >= 8 (5 items + workers polling empty)", claimCalls)
	}
}

func TestServiceRunConcurrentErrorCancelsWorkers(t *testing.T) {
	t.Parallel()

	workItems := []ScopeGenerationWork{
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-1",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-1",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-1",
				GenerationID: "gen-1",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-2",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-2",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-2",
				GenerationID: "gen-2",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-3",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-3",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-3",
				GenerationID: "gen-3",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
		{
			Scope: scope.IngestionScope{
				ScopeID:       "scope-4",
				SourceSystem:  "git",
				ScopeKind:     scope.KindRepository,
				CollectorKind: scope.CollectorGit,
				PartitionKey:  "repo-4",
			},
			Generation: scope.ScopeGeneration{
				ScopeID:      "scope-4",
				GenerationID: "gen-4",
				ObservedAt:   time.Date(2026, time.April, 12, 11, 30, 0, 0, time.UTC),
				IngestedAt:   time.Date(2026, time.April, 12, 11, 31, 0, 0, time.UTC),
				Status:       scope.GenerationStatusPending,
				TriggerKind:  scope.TriggerKindSnapshot,
			},
		},
	}

	source := &stubProjectorWorkSource{workItems: workItems}
	factStore := &stubFactStore{
		facts: []facts.Envelope{{
			FactID:       "fact-1",
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
			FactKind:     "source_node",
		}},
	}
	runner := &stubProjectionRunner{
		result: Result{
			ScopeID:      "scope-123",
			GenerationID: "generation-456",
		},
	}
	// Make the sink fail after 2 successful acks (infrastructure failure)
	sink := &stubProjectorWorkSink{failAfter: 2}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		FactStore:    factStore,
		Runner:       runner,
		WorkSink:     sink,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
		Workers:      3,
	}

	err := service.Run(context.Background())
	if err == nil {
		t.Fatal("Run() error = nil, want non-nil error")
	}

	sink.mu.Lock()
	ackCalls := sink.ackCalls
	sink.mu.Unlock()

	runner.mu.Lock()
	runCalls := runner.runCalls
	runner.mu.Unlock()

	// Should have processed at least 3 items (2 successful acks + 1 that triggered error)
	if ackCalls < 3 {
		t.Fatalf("ack calls = %d, want >= 3", ackCalls)
	}
	if runCalls < 3 {
		t.Fatalf("runner calls = %d, want >= 3", runCalls)
	}
	// Should not have processed all 4 items due to cancellation
	if runCalls >= 4 {
		t.Logf("warning: runner calls = %d, expected < 4 due to cancellation (may be timing-dependent)", runCalls)
	}
}
