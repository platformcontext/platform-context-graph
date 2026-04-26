package main

import (
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/query"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
)

func TestLoadReducerQueueConfigUsesDefaults(t *testing.T) {
	t.Parallel()

	cfg, err := loadReducerQueueConfig(func(string) string { return "" })
	if err != nil {
		t.Fatalf("loadReducerQueueConfig() error = %v, want nil", err)
	}

	if got, want := cfg.RetryDelay, 30*time.Second; got != want {
		t.Fatalf("retryDelay = %v, want %v", got, want)
	}
	if got, want := cfg.MaxAttempts, 3; got != want {
		t.Fatalf("maxAttempts = %d, want %d", got, want)
	}
}

func TestLoadReducerQueueConfigReadsEnvOverrides(t *testing.T) {
	t.Parallel()

	cfg, err := loadReducerQueueConfig(func(name string) string {
		switch name {
		case reducerRetryDelayEnv:
			return "2m"
		case reducerMaxAttemptsEnv:
			return "5"
		default:
			return ""
		}
	})
	if err != nil {
		t.Fatalf("loadReducerQueueConfig() error = %v, want nil", err)
	}

	if got, want := cfg.RetryDelay, 2*time.Minute; got != want {
		t.Fatalf("retryDelay = %v, want %v", got, want)
	}
	if got, want := cfg.MaxAttempts, 5; got != want {
		t.Fatalf("maxAttempts = %d, want %d", got, want)
	}
}

func TestLoadReducerWorkerCount_EnvOverride(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(k string) string {
		if k == reducerWorkersEnv {
			return "6"
		}
		return ""
	}, runtimecfg.GraphBackendNornicDB)
	if got != 6 {
		t.Fatalf("got %d, want 6", got)
	}
}

func TestLoadReducerWorkerCount_Neo4jDefaultCap(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(string) string { return "" }, runtimecfg.GraphBackendNeo4j)
	if got < 1 || got > 4 {
		t.Fatalf("got %d, want 1-4", got)
	}
}

func TestLoadReducerWorkerCount_NornicDBDefaultsSequential(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(string) string { return "" }, runtimecfg.GraphBackendNornicDB)
	if got != 1 {
		t.Fatalf("got %d, want 1", got)
	}
}

func TestLoadReducerWorkerCount_InvalidEnv(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(k string) string {
		if k == reducerWorkersEnv {
			return "not-a-number"
		}
		return ""
	}, runtimecfg.GraphBackendNornicDB)
	if got != 1 {
		t.Fatalf("got %d, want 1 for NornicDB fallback", got)
	}
}

func TestLoadReducerBatchClaimSize_EnvOverride(t *testing.T) {
	t.Parallel()

	got := loadReducerBatchClaimSize(func(k string) string {
		if k == reducerBatchClaimEnv {
			return "6"
		}
		return ""
	}, 2, runtimecfg.GraphBackendNornicDB)
	if got != 6 {
		t.Fatalf("got %d, want 6", got)
	}
}

func TestLoadReducerBatchClaimSize_Neo4jDefault(t *testing.T) {
	t.Parallel()

	got := loadReducerBatchClaimSize(func(string) string { return "" }, 3, runtimecfg.GraphBackendNeo4j)
	if got != 12 {
		t.Fatalf("got %d, want 12", got)
	}
}

func TestLoadReducerBatchClaimSize_NornicDBDefaultsSingleClaim(t *testing.T) {
	t.Parallel()

	got := loadReducerBatchClaimSize(func(string) string { return "" }, 2, runtimecfg.GraphBackendNornicDB)
	if got != 1 {
		t.Fatalf("got %d, want 1", got)
	}
}

func TestLoadReducerBatchClaimSize_InvalidEnvFallsBackToBackendDefault(t *testing.T) {
	t.Parallel()

	got := loadReducerBatchClaimSize(func(k string) string {
		if k == reducerBatchClaimEnv {
			return "nope"
		}
		return ""
	}, 2, runtimecfg.GraphBackendNornicDB)
	if got != 1 {
		t.Fatalf("got %d, want 1 for NornicDB fallback", got)
	}
}

func TestLoadReducerProjectorDrainGate_NornicDBLocalAuthoritative(t *testing.T) {
	t.Parallel()

	got, err := loadReducerProjectorDrainGate(func(k string) string {
		switch k {
		case queryProfileEnv:
			return string(query.ProfileLocalAuthoritative)
		default:
			return ""
		}
	}, runtimecfg.GraphBackendNornicDB)
	if err != nil {
		t.Fatalf("loadReducerProjectorDrainGate() error = %v, want nil", err)
	}
	if !got {
		t.Fatal("loadReducerProjectorDrainGate() = false, want true")
	}
}

func TestLoadReducerProjectorDrainGate_DisabledForNeo4j(t *testing.T) {
	t.Parallel()

	got, err := loadReducerProjectorDrainGate(func(k string) string {
		switch k {
		case queryProfileEnv:
			return string(query.ProfileLocalAuthoritative)
		default:
			return ""
		}
	}, runtimecfg.GraphBackendNeo4j)
	if err != nil {
		t.Fatalf("loadReducerProjectorDrainGate() error = %v, want nil", err)
	}
	if got {
		t.Fatal("loadReducerProjectorDrainGate() = true, want false")
	}
}

func TestLoadReducerProjectorDrainGate_DisabledWithoutLocalAuthoritativeProfile(t *testing.T) {
	t.Parallel()

	got, err := loadReducerProjectorDrainGate(func(string) string { return "" }, runtimecfg.GraphBackendNornicDB)
	if err != nil {
		t.Fatalf("loadReducerProjectorDrainGate() error = %v, want nil", err)
	}
	if got {
		t.Fatal("loadReducerProjectorDrainGate() = true, want false")
	}
}

func TestLoadReducerProjectorDrainGate_InvalidProfile(t *testing.T) {
	t.Parallel()

	_, err := loadReducerProjectorDrainGate(func(k string) string {
		if k == queryProfileEnv {
			return "definitely-not-a-profile"
		}
		return ""
	}, runtimecfg.GraphBackendNornicDB)
	if err == nil {
		t.Fatal("loadReducerProjectorDrainGate() error = nil, want non-nil")
	}
}
