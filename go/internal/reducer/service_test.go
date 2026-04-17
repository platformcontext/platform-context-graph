package reducer

import (
	"context"
	"errors"
	"log/slog"
	"sync"
	"testing"
	"time"

	metricnoop "go.opentelemetry.io/otel/metric/noop"
	"go.opentelemetry.io/otel/trace/noop"

	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestServiceRunClaimsExecutesAndAcknowledges(t *testing.T) {
	t.Parallel()

	intent := Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "projector emitted shared identity work",
		EntityKeys:      []string{"workload:pcg"},
		RelatedScopeIDs: []string{"scope-999"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		Status:          IntentStatusPending,
	}

	source := &stubReducerWorkSource{intents: []Intent{intent}}
	executor := &stubReducerExecutor{
		result: Result{
			IntentID: intent.IntentID,
			Domain:   intent.Domain,
			Status:   ResultStatusSucceeded,
		},
	}
	sink := &stubReducerWorkSink{}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		Executor:     executor,
		WorkSink:     sink,
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	if err := service.Run(context.Background()); err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	if got, want := source.claimCalls, 2; got != want {
		t.Fatalf("claim calls = %d, want %d", got, want)
	}
	if got, want := executor.executeCalls, 1; got != want {
		t.Fatalf("execute calls = %d, want %d", got, want)
	}
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
}

func TestServiceRunMarksFailureWhenExecutionFails(t *testing.T) {
	t.Parallel()

	intent := Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "projector emitted shared identity work",
		EntityKeys:      []string{"workload:pcg"},
		RelatedScopeIDs: []string{"scope-999"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		Status:          IntentStatusPending,
	}

	wantErr := errors.New("execution failed")
	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubReducerWorkSource{intents: []Intent{intent}},
		Executor:     &stubReducerExecutor{executeErr: wantErr},
		WorkSink:     &stubReducerWorkSink{},
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	sink := service.WorkSink.(*stubReducerWorkSink)

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

func TestServiceRunStartsSharedProjectionRunner(t *testing.T) {
	t.Parallel()

	leaseManager := &fakeLeaseManager{granted: false}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubReducerWorkSource{},
		Executor:     &stubReducerExecutor{},
		WorkSink:     &stubReducerWorkSink{},
		SharedProjectionRunner: &SharedProjectionRunner{
			IntentReader: &fakeSharedIntentReader{},
			LeaseManager: leaseManager,
			EdgeWriter:   &fakeEdgeWriter{},
			AcceptedGen:  func(_, _ string) (string, bool) { return "", false },
			Config: SharedProjectionRunnerConfig{
				PartitionCount: 1,
				PollInterval:   10 * time.Millisecond,
			},
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	err := service.Run(ctx)
	if err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	// Verify the shared projection runner attempted lease claims (proving it ran).
	leaseManager.mu.Lock()
	claims := leaseManager.claims
	leaseManager.mu.Unlock()

	if claims == 0 {
		t.Fatal("expected shared projection runner to attempt at least one lease claim")
	}
}

func TestServiceRunStartsCodeCallProjectionRunner(t *testing.T) {
	t.Parallel()

	store := &fakeCodeCallIntentStore{leaseGranted: false}

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubReducerWorkSource{},
		Executor:     &stubReducerExecutor{},
		WorkSink:     &stubReducerWorkSink{},
		CodeCallProjectionRunner: &CodeCallProjectionRunner{
			IntentReader: store,
			LeaseManager: store,
			EdgeWriter:   &recordingCodeCallProjectionEdgeWriter{},
			AcceptedGen:  func(_, _ string) (string, bool) { return "", false },
			Config: CodeCallProjectionRunnerConfig{
				PollInterval: 10 * time.Millisecond,
			},
		},
	}

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()

	err := service.Run(ctx)
	if err != nil {
		t.Fatalf("Run() error = %v, want nil", err)
	}

	store.mu.Lock()
	claims := store.claims
	store.mu.Unlock()

	if claims == 0 {
		t.Fatal("expected code call projection runner to attempt at least one lease claim")
	}
}

func TestServiceRunWorksWithoutSharedProjectionRunner(t *testing.T) {
	t.Parallel()

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   &stubReducerWorkSource{},
		Executor:     &stubReducerExecutor{},
		WorkSink:     &stubReducerWorkSink{},
		Wait:         func(context.Context, time.Duration) error { return context.Canceled },
	}

	err := service.Run(context.Background())
	if err != nil {
		t.Fatalf("Run() error = %v, want nil (should work without projection runner)", err)
	}
}

type stubReducerWorkSource struct {
	mu         sync.Mutex
	claimCalls int
	intents    []Intent
}

func (s *stubReducerWorkSource) Claim(context.Context) (Intent, bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.claimCalls++
	if len(s.intents) == 0 {
		return Intent{}, false, nil
	}

	intent := s.intents[0]
	s.intents = s.intents[1:]
	return intent, true, nil
}

type stubReducerExecutor struct {
	mu           sync.Mutex
	executeCalls int
	result       Result
	executeErr   error
}

func (s *stubReducerExecutor) Execute(context.Context, Intent) (Result, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.executeCalls++
	return s.result, s.executeErr
}

type stubReducerWorkSink struct {
	mu         sync.Mutex
	ackCalls   int
	failCalls  int
	failedWith error
	ackErr     error
}

func (s *stubReducerWorkSink) Ack(context.Context, Intent, Result) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.ackCalls++
	return s.ackErr
}

func (s *stubReducerWorkSink) Fail(_ context.Context, _ Intent, err error) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.failCalls++
	s.failedWith = err
	return nil
}

func TestServiceRunMainLoopWithTelemetry(t *testing.T) {
	t.Parallel()

	intent := Intent{
		IntentID:        "intent-1",
		ScopeID:         "scope-123",
		GenerationID:    "generation-456",
		SourceSystem:    "git",
		Domain:          DomainWorkloadIdentity,
		Cause:           "projector emitted shared identity work",
		EntityKeys:      []string{"workload:pcg"},
		RelatedScopeIDs: []string{"scope-999"},
		EnqueuedAt:      time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		AvailableAt:     time.Date(2026, time.April, 12, 11, 0, 0, 0, time.UTC),
		Status:          IntentStatusPending,
	}

	source := &stubReducerWorkSource{intents: []Intent{intent}}
	executor := &stubReducerExecutor{
		result: Result{
			IntentID: intent.IntentID,
			Domain:   intent.Domain,
			Status:   ResultStatusSucceeded,
		},
	}
	sink := &stubReducerWorkSink{}

	tracer := noop.NewTracerProvider().Tracer("test")
	meter := metricnoop.NewMeterProvider().Meter("test")
	instruments, err := telemetry.NewInstruments(meter)
	if err != nil {
		t.Fatalf("NewInstruments() error = %v", err)
	}
	logger := slog.Default()

	service := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		Executor:     executor,
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
	if got, want := executor.executeCalls, 1; got != want {
		t.Fatalf("execute calls = %d, want %d", got, want)
	}
	if got, want := sink.ackCalls, 1; got != want {
		t.Fatalf("ack calls = %d, want %d", got, want)
	}
	if got, want := sink.failCalls, 0; got != want {
		t.Fatalf("fail calls = %d, want %d", got, want)
	}
}
