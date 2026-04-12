package main

import (
	"testing"

	sourceneo4j "github.com/platformcontext/platform-context-graph/go/internal/storage/neo4j"
	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildProjectorRuntimeWiresPersistentStorageAdapters(t *testing.T) {
	t.Parallel()

	runtime := buildProjectorRuntime(postgres.SQLDB{}, sourceneo4j.Adapter{}, nil)

	if _, ok := runtime.GraphWriter.(sourceneo4j.Adapter); !ok {
		t.Fatalf("GraphWriter type = %T, want %T", runtime.GraphWriter, sourceneo4j.Adapter{})
	}
	if _, ok := runtime.ContentWriter.(postgres.ContentWriter); !ok {
		t.Fatalf("ContentWriter type = %T, want %T", runtime.ContentWriter, postgres.ContentWriter{})
	}
}

func TestCloseProjectorNeo4jDriverAllowsNilDriver(t *testing.T) {
	t.Parallel()

	if err := closeProjectorNeo4jDriver(nil); err != nil {
		t.Fatalf("closeProjectorNeo4jDriver(nil) error = %v, want nil", err)
	}
}
