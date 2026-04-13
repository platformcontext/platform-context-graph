package main

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

// runnerFunc adapts a plain function into the app.Runner interface for tests.
type runnerFunc func(context.Context) error

func (f runnerFunc) Run(ctx context.Context) error { return f(ctx) }

var _ app.Runner = runnerFunc(nil)

func TestBuildIngesterServiceProducesCompositeRunner(t *testing.T) {
	t.Parallel()

	runner, err := buildIngesterService(
		postgres.SQLDB{},
		&graph.MemoryWriter{},
		func(string) string { return "" },
		func() (string, error) { return t.TempDir(), nil },
		func() []string { return []string{"PATH=/usr/bin"} },
		nil, // tracer
		nil, // instruments
		nil, // logger
	)
	if err != nil {
		t.Fatalf("buildIngesterService() error = %v, want nil", err)
	}
	if len(runner.runners) != 2 {
		t.Fatalf("buildIngesterService() runner count = %d, want 2", len(runner.runners))
	}
}

func TestBuildIngesterCollectorServiceUsesNativeSnapshotter(t *testing.T) {
	t.Parallel()

	service, err := buildIngesterCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return t.TempDir(), nil },
		func() []string { return []string{"PATH=/usr/bin"} },
		nil, // tracer
		nil, // instruments
		nil, // logger
	)
	if err != nil {
		t.Fatalf("buildIngesterCollectorService() error = %v, want nil", err)
	}

	source, ok := service.Source.(*collector.GitSource)
	if !ok {
		t.Fatalf("buildIngesterCollectorService() source type = %T, want *collector.GitSource", service.Source)
	}
	if _, ok := source.Selector.(collector.NativeRepositorySelector); !ok {
		t.Fatalf("buildIngesterCollectorService() selector type = %T, want collector.NativeRepositorySelector", source.Selector)
	}
	if _, ok := source.Snapshotter.(collector.NativeRepositorySnapshotter); !ok {
		t.Fatalf("buildIngesterCollectorService() snapshotter type = %T, want collector.NativeRepositorySnapshotter", source.Snapshotter)
	}
}

func TestCompositeRunnerCancelsOnFirstError(t *testing.T) {
	t.Parallel()

	expectedErr := errors.New("runner failed")
	blocked := make(chan struct{})

	runner := compositeRunner{
		runners: []app.Runner{
			runnerFunc(func(ctx context.Context) error {
				return expectedErr
			}),
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				close(blocked)
				return nil
			}),
		},
	}

	err := runner.Run(context.Background())
	if !errors.Is(err, expectedErr) {
		t.Fatalf("compositeRunner.Run() error = %v, want %v", err, expectedErr)
	}

	select {
	case <-blocked:
	case <-time.After(5 * time.Second):
		t.Fatal("compositeRunner.Run() did not cancel remaining runners")
	}
}

func TestCompositeRunnerExitsOnContextCancel(t *testing.T) {
	t.Parallel()

	runner := compositeRunner{
		runners: []app.Runner{
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				return nil
			}),
			runnerFunc(func(ctx context.Context) error {
				<-ctx.Done()
				return nil
			}),
		},
	}

	ctx, cancel := context.WithCancel(context.Background())
	cancel()

	err := runner.Run(ctx)
	if err != nil {
		t.Fatalf("compositeRunner.Run() error = %v, want nil", err)
	}
}
