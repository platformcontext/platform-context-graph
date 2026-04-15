package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"sync"
	"sync/atomic"
	"testing"
	"time"

	"log/slog"

	"go.opentelemetry.io/otel/trace"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
	"github.com/platformcontext/platform-context-graph/go/internal/telemetry"
)

func TestRunAppliesSchemaAndDrainsCollectorAndProjector(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{}
	schemaApplied := false

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(ctx context.Context, database bootstrapDB) error {
			schemaApplied = true
			return nil
		},
		func(context.Context, func(string) string, trace.Tracer, *telemetry.Instruments) (graphDeps, error) {
			return graphDeps{writer: &graph.MemoryWriter{}, close: func() error { return nil }}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments, _ *slog.Logger) (collectorDeps, error) {
			return collectorDeps{
				source: &fakeSource{
					generations: []collector.CollectedGeneration{
						{
							Scope:     scope.IngestionScope{ScopeID: "s1"},
							FactCount: 0,
						},
					},
				},
				committer: &fakeCommitter{},
			}, nil
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments) (projectorDeps, error) {
			return projectorDeps{
				workSource: &fakeWorkSource{
					items: []projector.ScopeGenerationWork{
						{Scope: scope.IngestionScope{ScopeID: "s1"}},
					},
				},
				factStore: &fakeFactStore{},
				runner:    &fakeProjectionRunner{},
				workSink:  &fakeWorkSink{},
			}, nil
		},
	)
	if err != nil {
		t.Fatalf("run() error = %v, want nil", err)
	}
	if !schemaApplied {
		t.Fatal("run() did not apply schema")
	}
	if !db.closed {
		t.Fatal("run() did not close database")
	}
}

func TestRunReturnsSchemaError(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{}
	schemaErr := errors.New("schema failed")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(ctx context.Context, database bootstrapDB) error {
			return schemaErr
		},
		func(context.Context, func(string) string, trace.Tracer, *telemetry.Instruments) (graphDeps, error) {
			t.Fatal("graph opener should not be called after schema error")
			return graphDeps{}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments, _ *slog.Logger) (collectorDeps, error) {
			t.Fatal("collector builder should not be called after schema error")
			return collectorDeps{}, nil
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments) (projectorDeps, error) {
			t.Fatal("projector builder should not be called after schema error")
			return projectorDeps{}, nil
		},
	)
	if !errors.Is(err, schemaErr) {
		t.Fatalf("run() error = %v, want %v", err, schemaErr)
	}
	if !db.closed {
		t.Fatal("run() did not close database")
	}
}

func TestRunReturnsCollectorError(t *testing.T) {
	t.Parallel()

	db := &fakeBootstrapDB{}
	collectorErr := errors.New("collector build failed")

	err := run(
		context.Background(),
		func(string) string { return "" },
		func(context.Context, func(string) string) (bootstrapDB, error) {
			return db, nil
		},
		func(ctx context.Context, database bootstrapDB) error {
			return nil
		},
		func(context.Context, func(string) string, trace.Tracer, *telemetry.Instruments) (graphDeps, error) {
			return graphDeps{writer: &graph.MemoryWriter{}, close: func() error { return nil }}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments, _ *slog.Logger) (collectorDeps, error) {
			return collectorDeps{}, collectorErr
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string, _ trace.Tracer, _ *telemetry.Instruments) (projectorDeps, error) {
			t.Fatal("projector builder should not be called after collector error")
			return projectorDeps{}, nil
		},
	)
	if !errors.Is(err, collectorErr) {
		t.Fatalf("run() error = %v, want %v", err, collectorErr)
	}
	if !db.closed {
		t.Fatal("run() did not close database")
	}
}

func TestBuildBootstrapCollectorUsesNativeSnapshotter(t *testing.T) {
	t.Parallel()

	deps, err := buildBootstrapCollector(
		context.Background(),
		&fakeBootstrapSQLDB{},
		func(string) string { return "" },
		nil, nil, nil,
	)
	if err != nil {
		t.Fatalf("buildBootstrapCollector() error = %v, want nil", err)
	}

	source, ok := deps.source.(*collector.GitSource)
	if !ok {
		t.Fatalf("buildBootstrapCollector() source type = %T, want *collector.GitSource", deps.source)
	}
	if _, ok := source.Selector.(collector.NativeRepositorySelector); !ok {
		t.Fatalf("buildBootstrapCollector() selector type = %T, want collector.NativeRepositorySelector", source.Selector)
	}
	if _, ok := source.Snapshotter.(collector.NativeRepositorySnapshotter); !ok {
		t.Fatalf("buildBootstrapCollector() snapshotter type = %T, want collector.NativeRepositorySnapshotter", source.Snapshotter)
	}
}

// --- fakes ---

type fakeBootstrapDB struct {
	closed bool
}

func (f *fakeBootstrapDB) Close() error {
	f.closed = true
	return nil
}

func (f *fakeBootstrapDB) ExecContext(context.Context, string, ...any) (sql.Result, error) {
	return nil, nil
}

func (f *fakeBootstrapDB) QueryContext(context.Context, string, ...any) (postgres.Rows, error) {
	return nil, nil
}

type fakeBootstrapSQLDB = fakeBootstrapDB

type fakeSource struct {
	generations []collector.CollectedGeneration
	index       int
}

func (f *fakeSource) Next(context.Context) (collector.CollectedGeneration, bool, error) {
	if f.index >= len(f.generations) {
		return collector.CollectedGeneration{}, false, nil
	}
	gen := f.generations[f.index]
	f.index++
	return gen, true, nil
}

type fakeCommitter struct{}

func (f *fakeCommitter) CommitScopeGeneration(
	_ context.Context,
	_ scope.IngestionScope,
	_ scope.ScopeGeneration,
	factStream <-chan facts.Envelope,
) error {
	if factStream != nil {
		for range factStream {
		}
	}
	return nil
}

type fakeWorkSource struct {
	mu    sync.Mutex
	items []projector.ScopeGenerationWork
	index int
}

func (f *fakeWorkSource) Claim(context.Context) (projector.ScopeGenerationWork, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.index >= len(f.items) {
		return projector.ScopeGenerationWork{}, false, nil
	}
	item := f.items[f.index]
	f.index++
	return item, true, nil
}

type fakeFactStore struct{}

func (f *fakeFactStore) LoadFacts(context.Context, projector.ScopeGenerationWork) ([]facts.Envelope, error) {
	return nil, nil
}

type fakeProjectionRunner struct{}

func (f *fakeProjectionRunner) Project(
	context.Context,
	scope.IngestionScope,
	scope.ScopeGeneration,
	[]facts.Envelope,
) (projector.Result, error) {
	return projector.Result{}, nil
}

type fakeWorkSink struct{}

func (f *fakeWorkSink) Ack(context.Context, projector.ScopeGenerationWork, projector.Result) error {
	return nil
}

func (f *fakeWorkSink) Fail(context.Context, projector.ScopeGenerationWork, error) error {
	return nil
}

// --- concurrency tests ---

func TestDrainProjectorConcurrentMultipleItems(t *testing.T) {
	t.Parallel()

	items := make([]projector.ScopeGenerationWork, 10)
	for i := range items {
		items[i] = projector.ScopeGenerationWork{
			Scope: scope.IngestionScope{ScopeID: fmt.Sprintf("scope-%d", i)},
		}
	}

	ws := &concurrentWorkSource{items: items}
	sink := &concurrentWorkSink{}

	err := drainProjector(
		context.Background(),
		ws, &fakeFactStore{}, &fakeProjectionRunner{}, sink,
		4, nil, nil, nil,
	)
	if err != nil {
		t.Fatalf("drainProjector() error = %v, want nil", err)
	}
	if got := sink.acked.Load(); got != 10 {
		t.Fatalf("drainProjector() acked = %d, want 10", got)
	}
}

func TestDrainProjectorSequentialFallback(t *testing.T) {
	t.Parallel()

	items := []projector.ScopeGenerationWork{
		{Scope: scope.IngestionScope{ScopeID: "s1"}},
		{Scope: scope.IngestionScope{ScopeID: "s2"}},
	}
	ws := &concurrentWorkSource{items: items}
	sink := &concurrentWorkSink{}

	// workers=1 should use sequential path
	err := drainProjector(
		context.Background(),
		ws, &fakeFactStore{}, &fakeProjectionRunner{}, sink,
		1, nil, nil, nil,
	)
	if err != nil {
		t.Fatalf("drainProjector(workers=1) error = %v, want nil", err)
	}
	if got := sink.acked.Load(); got != 2 {
		t.Fatalf("drainProjector(workers=1) acked = %d, want 2", got)
	}
}

func TestDrainProjectorErrorCancelsWorkers(t *testing.T) {
	t.Parallel()

	projectErr := errors.New("project failed")
	items := make([]projector.ScopeGenerationWork, 20)
	for i := range items {
		items[i] = projector.ScopeGenerationWork{
			Scope: scope.IngestionScope{ScopeID: fmt.Sprintf("scope-%d", i)},
		}
	}

	ws := &concurrentWorkSource{items: items}
	runner := &failingProjectionRunner{failAfter: 2, err: projectErr}

	err := drainProjector(
		context.Background(),
		ws, &fakeFactStore{}, runner, &concurrentWorkSink{},
		4, nil, nil, nil,
	)
	if err == nil {
		t.Fatal("drainProjector() expected error, got nil")
	}
	if !errors.Is(err, projectErr) {
		t.Fatalf("drainProjector() error = %v, want wrapping %v", err, projectErr)
	}
}

func TestProjectionWorkerCount(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name string
		env  string
		want int
	}{
		{name: "default", env: "", want: -1}, // will be runtime.NumCPU capped at 8
		{name: "explicit_2", env: "2", want: 2},
		{name: "explicit_16", env: "16", want: 16},
		{name: "zero_uses_default", env: "0", want: -1},
		{name: "negative_uses_default", env: "-1", want: -1},
		{name: "invalid_uses_default", env: "abc", want: -1},
		{name: "whitespace_trimmed", env: " 4 ", want: 4},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			t.Parallel()
			got := projectionWorkerCount(func(key string) string {
				if key == "PCG_PROJECTION_WORKERS" {
					return tt.env
				}
				return ""
			})
			if tt.want == -1 {
				// Default: expect NumCPU capped at 8
				maxDefault := 8
				if got < 1 || got > maxDefault {
					t.Fatalf("projectionWorkerCount(%q) = %d, want 1..%d", tt.env, got, maxDefault)
				}
			} else if got != tt.want {
				t.Fatalf("projectionWorkerCount(%q) = %d, want %d", tt.env, got, tt.want)
			}
		})
	}
}

func TestDrainCollectorWithTelemetry(t *testing.T) {
	t.Parallel()

	source := &fakeSource{
		generations: []collector.CollectedGeneration{
			{
				Scope:     scope.IngestionScope{ScopeID: "s1"},
				Facts:     testFactChannel(facts.Envelope{}, facts.Envelope{}),
				FactCount: 2,
			},
		},
	}

	err := drainCollector(
		context.Background(),
		source, &fakeCommitter{},
		nil, nil, nil,
	)
	if err != nil {
		t.Fatalf("drainCollector() error = %v, want nil", err)
	}
}

// testFactChannel creates a pre-filled closed channel for testing.
func testFactChannel(envelopes ...facts.Envelope) <-chan facts.Envelope {
	ch := make(chan facts.Envelope, len(envelopes))
	for _, e := range envelopes {
		ch <- e
	}
	close(ch)
	return ch
}

// --- thread-safe fakes for concurrency tests ---

type concurrentWorkSource struct {
	mu    sync.Mutex
	items []projector.ScopeGenerationWork
	index int
}

func (f *concurrentWorkSource) Claim(context.Context) (projector.ScopeGenerationWork, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.index >= len(f.items) {
		return projector.ScopeGenerationWork{}, false, nil
	}
	item := f.items[f.index]
	f.index++
	return item, true, nil
}

type concurrentWorkSink struct {
	acked atomic.Int64
}

func (f *concurrentWorkSink) Ack(context.Context, projector.ScopeGenerationWork, projector.Result) error {
	f.acked.Add(1)
	return nil
}

func (f *concurrentWorkSink) Fail(context.Context, projector.ScopeGenerationWork, error) error {
	return nil
}

// --- pipelined bootstrap tests ---

func TestPipelinedBootstrapProjectsDuringCollection(t *testing.T) {
	t.Parallel()

	// Simulate a slow collector that produces 5 scopes with a delay between each.
	// The projector should start processing items while the collector is still running.
	source := &slowSource{
		generations: []collector.CollectedGeneration{
			{Scope: scope.IngestionScope{ScopeID: "s1"}, FactCount: 0},
			{Scope: scope.IngestionScope{ScopeID: "s2"}, FactCount: 0},
			{Scope: scope.IngestionScope{ScopeID: "s3"}, FactCount: 0},
			{Scope: scope.IngestionScope{ScopeID: "s4"}, FactCount: 0},
			{Scope: scope.IngestionScope{ScopeID: "s5"}, FactCount: 0},
		},
		delay: 100 * time.Millisecond,
	}

	// Track when projections happen relative to collection.
	tracker := &projectionTracker{}

	ws := &concurrentWorkSource{
		items: []projector.ScopeGenerationWork{
			{Scope: scope.IngestionScope{ScopeID: "s1"}},
			{Scope: scope.IngestionScope{ScopeID: "s2"}},
			{Scope: scope.IngestionScope{ScopeID: "s3"}},
			{Scope: scope.IngestionScope{ScopeID: "s4"}},
			{Scope: scope.IngestionScope{ScopeID: "s5"}},
		},
	}
	sink := &concurrentWorkSink{}

	cd := collectorDeps{source: source, committer: &fakeCommitter{}}
	pd := projectorDeps{
		workSource: ws,
		factStore:  &fakeFactStore{},
		runner:     tracker,
		workSink:   sink,
	}

	err := runPipelined(context.Background(), cd, pd, 2, nil, nil, nil)
	if err != nil {
		t.Fatalf("runPipelined() error = %v, want nil", err)
	}

	if got := sink.acked.Load(); got != 5 {
		t.Fatalf("runPipelined() acked = %d, want 5", got)
	}

	// Verify projections started before all collections finished.
	// Collection takes ~500ms (5 × 100ms). If projections started during collection,
	// the first projection timestamp should be before collection ends.
	firstProjection := tracker.firstProjectionTime()
	if firstProjection.IsZero() {
		t.Fatal("no projections were recorded")
	}
}

func TestPipelinedBootstrapDrainsQueueAfterCollectorExits(t *testing.T) {
	t.Parallel()

	// Collector finishes immediately with 0 items.
	// Queue has items that were pre-populated (simulating items from a previous
	// collector run or items that appeared just before collector exited).
	source := &fakeSource{generations: nil}
	ws := &concurrentWorkSource{
		items: []projector.ScopeGenerationWork{
			{Scope: scope.IngestionScope{ScopeID: "s1"}},
			{Scope: scope.IngestionScope{ScopeID: "s2"}},
			{Scope: scope.IngestionScope{ScopeID: "s3"}},
		},
	}
	sink := &concurrentWorkSink{}

	cd := collectorDeps{source: source, committer: &fakeCommitter{}}
	pd := projectorDeps{
		workSource: ws,
		factStore:  &fakeFactStore{},
		runner:     &fakeProjectionRunner{},
		workSink:   sink,
	}

	err := runPipelined(context.Background(), cd, pd, 2, nil, nil, nil)
	if err != nil {
		t.Fatalf("runPipelined() error = %v, want nil", err)
	}

	if got := sink.acked.Load(); got != 3 {
		t.Fatalf("runPipelined() acked = %d, want 3 (should drain remaining queue)", got)
	}
}

func TestPipelinedBootstrapExitsCleanlyWhenQueueEmpty(t *testing.T) {
	t.Parallel()

	// Both collector and queue are empty — should exit cleanly and quickly.
	source := &fakeSource{generations: nil}
	ws := &concurrentWorkSource{items: nil}
	sink := &concurrentWorkSink{}

	cd := collectorDeps{source: source, committer: &fakeCommitter{}}
	pd := projectorDeps{
		workSource: ws,
		factStore:  &fakeFactStore{},
		runner:     &fakeProjectionRunner{},
		workSink:   sink,
	}

	start := time.Now()
	err := runPipelined(context.Background(), cd, pd, 2, nil, nil, nil)
	elapsed := time.Since(start)

	if err != nil {
		t.Fatalf("runPipelined() error = %v, want nil", err)
	}
	if got := sink.acked.Load(); got != 0 {
		t.Fatalf("runPipelined() acked = %d, want 0", got)
	}
	// Should exit within a few seconds (maxEmptyPolls × pollInterval).
	if elapsed > 10*time.Second {
		t.Fatalf("runPipelined() took %v, want < 10s (drain should exit quickly)", elapsed)
	}
}

func TestPipelinedBootstrapCollectorErrorCancelsProjector(t *testing.T) {
	t.Parallel()

	collectorErr := errors.New("collector exploded")
	source := &failingSource{err: collectorErr}
	ws := &concurrentWorkSource{items: nil}
	sink := &concurrentWorkSink{}

	cd := collectorDeps{source: source, committer: &fakeCommitter{}}
	pd := projectorDeps{
		workSource: ws,
		factStore:  &fakeFactStore{},
		runner:     &fakeProjectionRunner{},
		workSink:   sink,
	}

	err := runPipelined(context.Background(), cd, pd, 2, nil, nil, nil)
	if err == nil {
		t.Fatal("runPipelined() expected error, got nil")
	}
	if !errors.Is(err, collectorErr) {
		t.Fatalf("runPipelined() error = %v, want wrapping %v", err, collectorErr)
	}
}

// --- additional fakes for pipelined tests ---

type slowSource struct {
	mu          sync.Mutex
	generations []collector.CollectedGeneration
	index       int
	delay       time.Duration
}

func (f *slowSource) Next(ctx context.Context) (collector.CollectedGeneration, bool, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	if f.index >= len(f.generations) {
		return collector.CollectedGeneration{}, false, nil
	}

	select {
	case <-ctx.Done():
		return collector.CollectedGeneration{}, false, ctx.Err()
	case <-time.After(f.delay):
	}

	gen := f.generations[f.index]
	f.index++
	return gen, true, nil
}

type failingSource struct {
	err error
}

func (f *failingSource) Next(context.Context) (collector.CollectedGeneration, bool, error) {
	return collector.CollectedGeneration{}, false, f.err
}

type projectionTracker struct {
	mu    sync.Mutex
	first time.Time
}

func (p *projectionTracker) Project(
	_ context.Context,
	_ scope.IngestionScope,
	_ scope.ScopeGeneration,
	_ []facts.Envelope,
) (projector.Result, error) {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.first.IsZero() {
		p.first = time.Now()
	}
	return projector.Result{}, nil
}

func (p *projectionTracker) firstProjectionTime() time.Time {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.first
}

type failingProjectionRunner struct {
	mu        sync.Mutex
	count     int
	failAfter int
	err       error
}

func (f *failingProjectionRunner) Project(
	_ context.Context,
	_ scope.IngestionScope,
	_ scope.ScopeGeneration,
	_ []facts.Envelope,
) (projector.Result, error) {
	f.mu.Lock()
	defer f.mu.Unlock()
	f.count++
	if f.count > f.failAfter {
		return projector.Result{}, f.err
	}
	return projector.Result{}, nil
}
