package main

import (
	"context"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildProjectorRuntimeWiresPersistentStorageAdapters(t *testing.T) {
	t.Parallel()

	runtime := buildProjectorRuntime(postgres.SQLDB{}, sourceneo4j.Adapter{}, nil, nil)

	if _, ok := runtime.GraphWriter.(sourceneo4j.Adapter); !ok {
		t.Fatalf("GraphWriter type = %T, want %T", runtime.GraphWriter, sourceneo4j.Adapter{})
	}
	if _, ok := runtime.ContentWriter.(postgres.ContentWriter); !ok {
		t.Fatalf("ContentWriter type = %T, want %T", runtime.ContentWriter, postgres.ContentWriter{})
	}
}

func TestBuildProjectorServiceWiresRetryInjectorFromEnv(t *testing.T) {
	t.Parallel()

	service, err := buildProjectorService(
		postgres.SQLDB{},
		sourceneo4j.Adapter{},
		func(name string) string {
			if name == projectorRetryOnceScopeGenerationEnv {
				return "scope-123:generation-456"
			}
			return ""
		},
	)
	if err != nil {
		t.Fatalf("buildProjectorService() error = %v, want nil", err)
	}

	runtime, ok := service.Runner.(projector.Runtime)
	if !ok {
		t.Fatalf("Runner type = %T, want projector.Runtime", service.Runner)
	}
	if runtime.RetryInjector == nil {
		t.Fatal("RetryInjector = nil, want configured injector")
	}
}

func TestBuildProjectorServiceWiresRetryPolicyFromEnv(t *testing.T) {
	t.Parallel()

	service, err := buildProjectorService(
		postgres.SQLDB{},
		sourceneo4j.Adapter{},
		func(name string) string {
			switch name {
			case "PCG_PROJECTOR_MAX_ATTEMPTS":
				return "5"
			case "PCG_PROJECTOR_RETRY_DELAY":
				return "45s"
			default:
				return ""
			}
		},
	)
	if err != nil {
		t.Fatalf("buildProjectorService() error = %v, want nil", err)
	}

	workSource, ok := service.WorkSource.(postgres.ProjectorQueue)
	if !ok {
		t.Fatalf("WorkSource type = %T, want postgres.ProjectorQueue", service.WorkSource)
	}
	if got, want := workSource.MaxAttempts, 5; got != want {
		t.Fatalf("MaxAttempts = %d, want %d", got, want)
	}
	if got, want := workSource.RetryDelay, 45*time.Second; got != want {
		t.Fatalf("RetryDelay = %v, want %v", got, want)
	}
}

func TestCloseProjectorNeo4jDriverAllowsNilDriver(t *testing.T) {
	t.Parallel()

	if err := closeProjectorNeo4jDriver(nil); err != nil {
		t.Fatalf("closeProjectorNeo4jDriver(nil) error = %v, want nil", err)
	}
}

func TestNeo4jBatchSizeReturnsZeroWhenEmpty(t *testing.T) {
	t.Parallel()

	getenv := func(string) string { return "" }
	if got := neo4jBatchSize(getenv); got != 0 {
		t.Fatalf("neo4jBatchSize() = %d, want 0", got)
	}
}

func TestNeo4jBatchSizeParsesValidInteger(t *testing.T) {
	t.Parallel()

	getenv := func(string) string { return "500" }
	if got, want := neo4jBatchSize(getenv), 500; got != want {
		t.Fatalf("neo4jBatchSize() = %d, want %d", got, want)
	}
}

func TestNeo4jBatchSizeReturnsZeroForInvalidInput(t *testing.T) {
	t.Parallel()

	tests := []struct {
		name  string
		value string
	}{
		{"negative", "-10"},
		{"zero", "0"},
		{"non-numeric", "invalid"},
		{"whitespace", "   "},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			getenv := func(string) string { return tt.value }
			if got := neo4jBatchSize(getenv); got != 0 {
				t.Fatalf("neo4jBatchSize(%q) = %d, want 0", tt.value, got)
			}
		})
	}
}

// stubNeo4jExecutor is a no-op executor for tests that don't exercise Neo4j.
type stubNeo4jExecutor struct{}

func (stubNeo4jExecutor) Execute(_ context.Context, _ sourceneo4j.Statement) error { return nil }
