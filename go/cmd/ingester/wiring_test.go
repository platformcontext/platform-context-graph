package main

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/app"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

// runnerFunc adapts a plain function into the app.Runner interface for tests.
type runnerFunc func(context.Context) error

func (f runnerFunc) Run(ctx context.Context) error { return f(ctx) }

var _ app.Runner = runnerFunc(nil)

func TestBuildIngesterServiceProducesCompositeRunner(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	srcDir := filepath.Join(repoRoot, "src", "platform_context_graph")
	if err := os.MkdirAll(srcDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", srcDir, err)
	}

	runner, err := buildIngesterService(
		postgres.SQLDB{},
		&graph.MemoryWriter{},
		func(string) string { return "" },
		func() (string, error) { return repoRoot, nil },
		func() []string { return []string{"PATH=/usr/bin"} },
	)
	if err != nil {
		t.Fatalf("buildIngesterService() error = %v, want nil", err)
	}
	if len(runner.runners) != 2 {
		t.Fatalf("buildIngesterService() runner count = %d, want 2", len(runner.runners))
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
