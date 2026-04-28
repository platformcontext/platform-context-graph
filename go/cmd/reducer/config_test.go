package main

import (
	"runtime"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/query"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
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

func TestLoadReducerWorkerCount_NornicDBDefaultsToBoundedCPU(t *testing.T) {
	t.Parallel()
	got := loadReducerWorkerCount(func(string) string { return "" }, runtimecfg.GraphBackendNornicDB)
	if want := expectedNornicDBReducerWorkers(); got != want {
		t.Fatalf("got %d, want %d", got, want)
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
	if want := expectedNornicDBReducerWorkers(); got != want {
		t.Fatalf("got %d, want %d for NornicDB fallback", got, want)
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

func TestLoadReducerBatchClaimSize_NornicDBDefaultsToWorkerCount(t *testing.T) {
	t.Parallel()

	got := loadReducerBatchClaimSize(func(string) string { return "" }, 8, runtimecfg.GraphBackendNornicDB)
	if got != 8 {
		t.Fatalf("got %d, want 8", got)
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
	if got != 2 {
		t.Fatalf("got %d, want 2 for NornicDB fallback", got)
	}
}

func TestLoadReducerClaimDomain_DefaultsToAllDomains(t *testing.T) {
	t.Parallel()

	got, err := loadReducerClaimDomain(func(string) string { return "" })
	if err != nil {
		t.Fatalf("loadReducerClaimDomain() error = %v, want nil", err)
	}
	if got != "" {
		t.Fatalf("loadReducerClaimDomain() = %q, want empty domain filter", got)
	}
}

func TestLoadReducerClaimDomain_ParsesKnownDomain(t *testing.T) {
	t.Parallel()

	got, err := loadReducerClaimDomain(func(k string) string {
		if k == reducerClaimDomainEnv {
			return string(reducer.DomainSQLRelationshipMaterialization)
		}
		return ""
	})
	if err != nil {
		t.Fatalf("loadReducerClaimDomain() error = %v, want nil", err)
	}
	if got != reducer.DomainSQLRelationshipMaterialization {
		t.Fatalf("loadReducerClaimDomain() = %q, want %q", got, reducer.DomainSQLRelationshipMaterialization)
	}
}

func TestLoadReducerClaimDomain_RejectsUnknownDomain(t *testing.T) {
	t.Parallel()

	_, err := loadReducerClaimDomain(func(k string) string {
		if k == reducerClaimDomainEnv {
			return "not_a_domain"
		}
		return ""
	})
	if err == nil {
		t.Fatal("loadReducerClaimDomain() error = nil, want validation error")
	}
}

func expectedNornicDBReducerWorkers() int {
	n := runtime.NumCPU()
	if n > 8 {
		n = 8
	}
	if n < 1 {
		n = 1
	}
	return n
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

func TestLoadCodeCallProjectionConfigReadsAcceptanceScanLimit(t *testing.T) {
	t.Parallel()

	cfg := loadCodeCallProjectionConfig(func(k string) string {
		switch k {
		case codeCallProjectionBatchLimitEnv:
			return "250"
		case codeCallProjectionAcceptanceScanLimitEnv:
			return "20000"
		default:
			return ""
		}
	})

	if got, want := cfg.BatchLimit, 250; got != want {
		t.Fatalf("BatchLimit = %d, want %d", got, want)
	}
	if got, want := cfg.AcceptanceScanLimit, 20_000; got != want {
		t.Fatalf("AcceptanceScanLimit = %d, want %d", got, want)
	}
}

func TestLoadCodeCallProjectionConfigDefaultsAcceptanceScanLimit(t *testing.T) {
	t.Parallel()

	cfg := loadCodeCallProjectionConfig(func(string) string { return "" })

	if got, want := cfg.AcceptanceScanLimit, defaultCodeCallProjectionAcceptanceScanLimit; got != want {
		t.Fatalf("AcceptanceScanLimit = %d, want %d", got, want)
	}
}

func TestLoadCodeCallEdgeWriterTuningDefaultsToMeasuredLargeRepoBatch(t *testing.T) {
	t.Parallel()

	batchSize, groupBatchSize := loadCodeCallEdgeWriterTuning(func(string) string { return "" })

	if got, want := batchSize, 1000; got != want {
		t.Fatalf("batchSize = %d, want %d", got, want)
	}
	if got, want := groupBatchSize, defaultCodeCallEdgeGroupBatchSize; got != want {
		t.Fatalf("groupBatchSize = %d, want %d", got, want)
	}
}
