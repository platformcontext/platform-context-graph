package main

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/storage/postgres"
)

func TestBuildReducerServiceWiresDefaultRuntimeAndQueue(t *testing.T) {
	t.Parallel()

	service, err := buildReducerService(postgres.SQLDB{})
	if err != nil {
		t.Fatalf("buildReducerService() error = %v, want nil", err)
	}
	if service.PollInterval <= 0 {
		t.Fatalf("buildReducerService() poll interval = %v, want positive", service.PollInterval)
	}
	if service.WorkSource == nil {
		t.Fatal("buildReducerService() work source = nil, want non-nil")
	}
	if service.Executor == nil {
		t.Fatal("buildReducerService() executor = nil, want non-nil")
	}
	if service.WorkSink == nil {
		t.Fatal("buildReducerService() work sink = nil, want non-nil")
	}
}
