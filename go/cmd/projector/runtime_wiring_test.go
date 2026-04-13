package main

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

func TestLoadProjectorRetryInjectorBuildsInjectorFromEnv(t *testing.T) {
	t.Parallel()

	injector, err := loadProjectorRetryInjector(func(name string) string {
		if name == "PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION" {
			return "scope-123:generation-456"
		}
		return ""
	})
	if err != nil {
		t.Fatalf("loadProjectorRetryInjector() error = %v, want nil", err)
	}
	if injector == nil {
		t.Fatal("loadProjectorRetryInjector() = nil, want injector")
	}
	if _, ok := injector.(projector.RetryInjector); !ok {
		t.Fatalf("injector type = %T, want projector.RetryInjector", injector)
	}
}

func TestLoadProjectorRetryInjectorReturnsNilWhenUnset(t *testing.T) {
	t.Parallel()

	injector, err := loadProjectorRetryInjector(func(string) string { return "" })
	if err != nil {
		t.Fatalf("loadProjectorRetryInjector() error = %v, want nil", err)
	}
	if injector != nil {
		t.Fatalf("loadProjectorRetryInjector() = %T, want nil", injector)
	}
}
