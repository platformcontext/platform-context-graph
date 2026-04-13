package main

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/graph"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildIngesterServiceRejectsMissingBridgeRepoRoot(t *testing.T) {
	t.Parallel()

	_, err := buildIngesterService(
		postgres.SQLDB{},
		&graph.MemoryWriter{},
		func(string) string { return "" },
		func() (string, error) { return "/tmp/does-not-exist", nil },
		func() []string { return nil },
	)
	if err == nil {
		t.Fatal("buildIngesterService() error = nil, want non-nil")
	}
}
