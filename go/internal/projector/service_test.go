package projector

import (
	"context"
	"errors"
	"log/slog"
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
	claimCalls int
	workItems  []ScopeGenerationWork
}

func (s *stubProjectorWorkSource) Claim(context.Context) (ScopeGenerationWork, bool, error) {
	s.claimCalls++
	if len(s.workItems) == 0 {
		return ScopeGenerationWork{}, false, nil
	}

	work := s.workItems[0]
	s.workItems = s.workItems[1:]
	return work, true, nil
}

type stubFactStore struct {
	loadCalls int
	facts     []facts.Envelope
}

func (s *stubFactStore) LoadFacts(context.Context, ScopeGenerationWork) ([]facts.Envelope, error) {
	s.loadCalls++
	cloned := make([]facts.Envelope, len(s.facts))
	copy(cloned, s.facts)
	return cloned, nil
}

type stubProjectionRunner struct {
	runCalls int
	result   Result
	runErr   error
}

func (s *stubProjectionRunner) Project(ctx context.Context, scopeValue scope.IngestionScope, generation scope.ScopeGeneration, inputFacts []facts.Envelope) (Result, error) {
	s.runCalls++
	return s.result, s.runErr
}

type stubProjectorWorkSink struct {
	ackCalls   int
	failCalls  int
	failedWith error
}

func (s *stubProjectorWorkSink) Ack(context.Context, ScopeGenerationWork, Result) error {
	s.ackCalls++
	return nil
}

func (s *stubProjectorWorkSink) Fail(_ context.Context, _ ScopeGenerationWork, err error) error {
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
