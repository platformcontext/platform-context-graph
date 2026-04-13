package main

import (
	"context"
	"errors"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	"github.com/platformcontext/platform-context-graph/go/internal/scope"
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
		func(context.Context, func(string) string) (graphDeps, error) {
			return graphDeps{writer: &graph.MemoryWriter{}, close: func() error { return nil }}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string) (collectorDeps, error) {
			return collectorDeps{
				source: &fakeSource{
					generations: []collector.CollectedGeneration{
						{Scope: scope.IngestionScope{ScopeID: "s1"}},
					},
				},
				committer: &fakeCommitter{},
			}, nil
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string) (projectorDeps, error) {
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
		func(context.Context, func(string) string) (graphDeps, error) {
			t.Fatal("graph opener should not be called after schema error")
			return graphDeps{}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string) (collectorDeps, error) {
			t.Fatal("collector builder should not be called after schema error")
			return collectorDeps{}, nil
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string) (projectorDeps, error) {
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
		func(context.Context, func(string) string) (graphDeps, error) {
			return graphDeps{writer: &graph.MemoryWriter{}, close: func() error { return nil }}, nil
		},
		func(ctx context.Context, database bootstrapDB, getenv func(string) string) (collectorDeps, error) {
			return collectorDeps{}, collectorErr
		},
		func(ctx context.Context, database bootstrapDB, graphWriter graph.Writer, getenv func(string) string) (projectorDeps, error) {
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

// --- fakes ---

type fakeBootstrapDB struct {
	closed bool
}

func (f *fakeBootstrapDB) Close() error {
	f.closed = true
	return nil
}

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
	context.Context,
	scope.IngestionScope,
	scope.ScopeGeneration,
	[]facts.Envelope,
) error {
	return nil
}

type fakeWorkSource struct {
	items []projector.ScopeGenerationWork
	index int
}

func (f *fakeWorkSource) Claim(context.Context) (projector.ScopeGenerationWork, bool, error) {
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
