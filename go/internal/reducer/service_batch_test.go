package reducer

import (
	"context"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"
)

// fakeBatchWorkSource implements both WorkSource (single) and BatchWorkSource.
type fakeBatchWorkSource struct {
	mu      sync.Mutex
	intents []Intent
	claimed int
}

func (f *fakeBatchWorkSource) Claim(ctx context.Context) (Intent, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.intents) == 0 {
		return Intent{}, false, nil
	}
	intent := f.intents[0]
	f.intents = f.intents[1:]
	f.claimed++
	return intent, true, nil
}

func (f *fakeBatchWorkSource) ClaimBatch(_ context.Context, limit int) ([]Intent, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.intents) == 0 {
		return nil, nil
	}
	end := limit
	if end > len(f.intents) {
		end = len(f.intents)
	}
	batch := make([]Intent, end)
	copy(batch, f.intents[:end])
	f.intents = f.intents[end:]
	f.claimed += end
	return batch, nil
}

// fakeBatchWorkSink implements both WorkSink and BatchWorkSink.
type fakeBatchWorkSink struct {
	mu       sync.Mutex
	acked    int
	failed   int
	ackIDs   []string
	failedBy []string
}

func (f *fakeBatchWorkSink) Ack(_ context.Context, intent Intent, _ Result) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.acked++
	f.ackIDs = append(f.ackIDs, intent.IntentID)
	return nil
}

func (f *fakeBatchWorkSink) Fail(_ context.Context, intent Intent, _ error) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.failed++
	f.failedBy = append(f.failedBy, intent.IntentID)
	return nil
}

func (f *fakeBatchWorkSink) AckBatch(_ context.Context, intents []Intent, _ []Result) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.acked += len(intents)
	for _, intent := range intents {
		f.ackIDs = append(f.ackIDs, intent.IntentID)
	}
	return nil
}

type countingExecutor struct {
	count atomic.Int64
}

func (e *countingExecutor) Execute(_ context.Context, intent Intent) (Result, error) {
	e.count.Add(1)
	return Result{
		IntentID: intent.IntentID,
		Domain:   intent.Domain,
		Status:   ResultStatusSucceeded,
	}, nil
}

func makeTestIntents(n int) []Intent {
	intents := make([]Intent, n)
	for i := range intents {
		intents[i] = Intent{
			IntentID:        fmt.Sprintf("intent-%d", i),
			ScopeID:         "scope-1",
			GenerationID:    "gen-1",
			SourceSystem:    "git",
			Domain:          DomainCodeCallMaterialization,
			Cause:           "test",
			EntityKeys:      []string{fmt.Sprintf("key-%d", i)},
			RelatedScopeIDs: []string{"scope-1"},
			Status:          IntentStatusClaimed,
			EnqueuedAt:      time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC),
			AvailableAt:     time.Date(2026, 4, 15, 12, 0, 0, 0, time.UTC),
		}
	}
	return intents
}

func TestServiceRunBatchConcurrentProcessesAllItems(t *testing.T) {
	t.Parallel()

	intents := makeTestIntents(20)
	source := &fakeBatchWorkSource{intents: intents}
	sink := &fakeBatchWorkSink{}
	executor := &countingExecutor{}

	svc := Service{
		PollInterval:   10 * time.Millisecond,
		WorkSource:     source,
		Executor:       executor,
		WorkSink:       sink,
		Workers:        4,
		BatchClaimSize: 8,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := svc.runMainLoop(ctx)
	if err != nil {
		t.Fatalf("runMainLoop() error = %v", err)
	}

	if got := executor.count.Load(); got != 20 {
		t.Fatalf("executor count = %d, want 20", got)
	}
	sink.mu.Lock()
	acked := sink.acked
	sink.mu.Unlock()
	if acked != 20 {
		t.Fatalf("sink acked = %d, want 20", acked)
	}
}

func TestServiceFallsBackToPerItemWhenNoBatchInterface(t *testing.T) {
	t.Parallel()

	// Use a WorkSource that does NOT implement BatchWorkSource.
	intents := makeTestIntents(5)
	source := &nonBatchWorkSource{intents: intents}
	sink := &nonBatchWorkSink{}
	executor := &countingExecutor{}

	svc := Service{
		PollInterval: 10 * time.Millisecond,
		WorkSource:   source,
		Executor:     executor,
		WorkSink:     sink,
		Workers:      2,
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	err := svc.runMainLoop(ctx)
	if err != nil {
		t.Fatalf("runMainLoop() error = %v", err)
	}

	if got := executor.count.Load(); got != 5 {
		t.Fatalf("executor count = %d, want 5", got)
	}
}

// nonBatchWorkSource only implements WorkSource, not BatchWorkSource.
type nonBatchWorkSource struct {
	mu      sync.Mutex
	intents []Intent
}

func (f *nonBatchWorkSource) Claim(_ context.Context) (Intent, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if len(f.intents) == 0 {
		return Intent{}, false, nil
	}
	intent := f.intents[0]
	f.intents = f.intents[1:]
	return intent, true, nil
}

// nonBatchWorkSink only implements WorkSink, not BatchWorkSink.
type nonBatchWorkSink struct {
	mu    sync.Mutex
	acked int
}

func (f *nonBatchWorkSink) Ack(_ context.Context, _ Intent, _ Result) error {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.acked++
	return nil
}

func (f *nonBatchWorkSink) Fail(_ context.Context, _ Intent, _ error) error {
	return nil
}
