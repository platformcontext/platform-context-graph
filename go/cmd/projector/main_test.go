package main

import (
	"testing"

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

func TestCloseProjectorNeo4jDriverAllowsNilDriver(t *testing.T) {
	t.Parallel()

	if err := closeProjectorNeo4jDriver(nil); err != nil {
		t.Fatalf("closeProjectorNeo4jDriver(nil) error = %v, want nil", err)
	}
}
