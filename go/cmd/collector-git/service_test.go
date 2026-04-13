package main

import (
	"reflect"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/collector"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildCollectorServiceUsesIngestionStoreBoundary(t *testing.T) {
	t.Parallel()

	service, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return t.TempDir(), nil },
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
	if _, ok := source.Selector.(collector.NativeRepositorySelector); !ok {
		t.Fatalf("buildCollectorService() selector type = %T, want collector.NativeRepositorySelector", source.Selector)
	}
	if _, ok := source.Snapshotter.(collector.NativeRepositorySnapshotter); !ok {
		t.Fatalf("buildCollectorService() snapshotter type = %T, want collector.NativeRepositorySnapshotter", source.Snapshotter)
	}
	snapshotter := source.Snapshotter.(collector.NativeRepositorySnapshotter)
	if snapshotter.SCIP.Enabled {
		t.Fatal("buildCollectorService() SCIP enabled by default, want false")
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

func TestBuildCollectorServiceDoesNotRequireBridgeRepoRoot(t *testing.T) {
	t.Parallel()

	service, err := buildCollectorService(
		postgres.SQLDB{},
		func(string) string { return "" },
		func() (string, error) { return "/tmp/does-not-exist", nil },
		func() []string { return nil },
	)
	if err != nil {
		t.Fatalf("buildCollectorService() error = %v, want nil", err)
	}
	source, ok := service.Source.(*collector.GitSource)
	if !ok {
		t.Fatalf("buildCollectorService() source type = %T, want *collector.GitSource", service.Source)
	}
	if _, ok := source.Selector.(collector.NativeRepositorySelector); !ok {
		t.Fatalf("buildCollectorService() selector type = %T, want collector.NativeRepositorySelector", source.Selector)
	}
}

func TestBuildCollectorServiceWiresSCIPEnvironment(t *testing.T) {
	t.Parallel()

	service, err := buildCollectorService(
		postgres.SQLDB{},
		func(key string) string {
			switch key {
			case "SCIP_INDEXER":
				return "true"
			case "SCIP_LANGUAGES":
				return "python,go"
			default:
				return ""
			}
		},
		func() (string, error) { return t.TempDir(), nil },
		func() []string { return nil },
	)
	if err != nil {
		t.Fatalf("buildCollectorService() error = %v, want nil", err)
	}

	source := service.Source.(*collector.GitSource)
	snapshotter := source.Snapshotter.(collector.NativeRepositorySnapshotter)
	if !snapshotter.SCIP.Enabled {
		t.Fatal("SCIP enabled = false, want true")
	}
	if got, want := snapshotter.SCIP.Languages, []string{"python", "go"}; !reflect.DeepEqual(got, want) {
		t.Fatalf("SCIP languages = %#v, want %#v", got, want)
	}
}
