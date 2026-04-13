package main

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildIngesterServiceRejectsMissingBridgeRepoRoot(t *testing.T) {
	t.Parallel()

	runner, err := buildIngesterService(
		postgres.SQLDB{},
		&graph.MemoryWriter{},
		func(string) string { return "" },
		func() (string, error) { return "/tmp/does-not-exist", nil },
		func() []string { return nil },
		nil, // tracer
		nil, // instruments
		nil, // logger
	)
	if err != nil {
		t.Fatalf("buildIngesterService() error = %v, want nil", err)
	}
	if got, want := len(runner.runners), 2; got != want {
		t.Fatalf("len(buildIngesterService().runners) = %d, want %d", got, want)
	}
}
