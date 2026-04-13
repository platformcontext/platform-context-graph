package main

import (
	"os"
	"path/filepath"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	pythonbridge "github.com/platformcontext/platform-context-graph/go/internal/compatibility/pythonbridge"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildCollectorServiceUsesIngestionStoreBoundary(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	srcDir := filepath.Join(repoRoot, "src", "platform_context_graph")
	if err := os.MkdirAll(srcDir, 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v", srcDir, err)
	}

	service, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return repoRoot, nil },
		func() []string { return []string{"PATH=/usr/bin"} },
	)
	if err != nil {
		t.Fatalf("buildCollectorService() error = %v, want nil", err)
	}
	if service.Source == nil {
		t.Fatal("buildCollectorService() source = nil, want non-nil")
	}
	if _, ok := service.Source.(*collector.GitSource); !ok {
		t.Fatalf(
			"buildCollectorService() source type = %T, want *collector.GitSource",
			service.Source,
		)
	}
	source := service.Source.(*collector.GitSource)
	if _, ok := source.Selector.(pythonbridge.GitSelectionRunner); !ok {
		t.Fatalf("buildCollectorService() selector type = %T, want pythonbridge.GitSelectionRunner", source.Selector)
	}
	if _, ok := source.Snapshotter.(pythonbridge.GitRepositorySnapshotRunner); !ok {
		t.Fatalf("buildCollectorService() snapshotter type = %T, want pythonbridge.GitRepositorySnapshotRunner", source.Snapshotter)
	}
	if service.PollInterval <= 0 {
		t.Fatalf(
			"buildCollectorService() poll interval = %v, want positive",
			service.PollInterval,
		)
	}
	if _, ok := service.Committer.(postgres.IngestionStore); !ok {
		t.Fatalf(
			"buildCollectorService() committer type = %T, want postgres.IngestionStore",
			service.Committer,
		)
	}
}

func TestBuildCollectorServiceRejectsMissingBridgeRepoRoot(t *testing.T) {
	t.Parallel()

	_, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return "/tmp/does-not-exist", nil },
		func() []string { return nil },
	)
	if err == nil {
		t.Fatal("buildCollectorService() error = nil, want non-nil")
	}
}
