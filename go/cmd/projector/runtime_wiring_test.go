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

func TestLoadProjectorRetryPolicyReadsSharedRetryConfig(t *testing.T) {
	t.Parallel()

	cfg, err := loadProjectorRetryPolicy(func(name string) string {
		switch name {
		case "PCG_PROJECTOR_MAX_ATTEMPTS":
			return "4"
		case "PCG_PROJECTOR_RETRY_DELAY":
			return "42s"
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("loadProjectorRetryPolicy() error = %v, want nil", err)
	}
	if got, want := cfg.MaxAttempts, 4; got != want {
		t.Fatalf("MaxAttempts = %d, want %d", got, want)
	}
	if got, want := cfg.RetryDelay.Seconds(), 42.0; got != want {
		t.Fatalf("RetryDelay = %v, want 42s", cfg.RetryDelay)
	}
}
