package main

import (
	"runtime"
	"strconv"
	"strings"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
)

const (
	reducerRetryDelayEnv  = "PCG_REDUCER_RETRY_DELAY"
	reducerMaxAttemptsEnv = "PCG_REDUCER_MAX_ATTEMPTS"

	codeCallProjectionPollIntervalEnv = "PCG_CODE_CALL_PROJECTION_POLL_INTERVAL"
	codeCallProjectionLeaseTTLEnv     = "PCG_CODE_CALL_PROJECTION_LEASE_TTL"
	codeCallProjectionBatchLimitEnv   = "PCG_CODE_CALL_PROJECTION_BATCH_LIMIT"
	codeCallProjectionLeaseOwnerEnv   = "PCG_CODE_CALL_PROJECTION_LEASE_OWNER"
	codeCallEdgeBatchSizeEnv          = "PCG_CODE_CALL_EDGE_BATCH_SIZE"
	codeCallEdgeGroupBatchSizeEnv     = "PCG_CODE_CALL_EDGE_GROUP_BATCH_SIZE"

	graphProjectionRepairPollIntervalEnv = "PCG_GRAPH_PROJECTION_REPAIR_POLL_INTERVAL"
	graphProjectionRepairBatchLimitEnv   = "PCG_GRAPH_PROJECTION_REPAIR_BATCH_LIMIT"
	graphProjectionRepairRetryDelayEnv   = "PCG_GRAPH_PROJECTION_REPAIR_RETRY_DELAY"

	defaultCodeCallProjectionPollInterval = 500 * time.Millisecond
	defaultCodeCallProjectionLeaseTTL     = 60 * time.Second
	defaultCodeCallProjectionBatchLimit   = 100
	defaultCodeCallProjectionLeaseOwner   = "code-call-projection-runner"
	defaultCodeCallEdgeBatchSize          = 50
	defaultCodeCallEdgeGroupBatchSize     = 1

	defaultGraphProjectionRepairPollInterval = time.Second
	defaultGraphProjectionRepairBatchLimit   = 100
	defaultGraphProjectionRepairRetryDelay   = time.Minute
)

func loadReducerQueueConfig(getenv func(string) string) (runtimecfg.RetryPolicyConfig, error) {
	if getenv == nil {
		getenv = func(string) string { return "" }
	}

	return runtimecfg.LoadRetryPolicyConfig(getenv, "REDUCER")
}

func loadReducerBatchClaimSize(getenv func(string) string, workers int) int {
	if raw := strings.TrimSpace(getenv("PCG_REDUCER_BATCH_CLAIM_SIZE")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := workers * 4
	if n > 64 {
		n = 64
	}
	if n < 4 {
		n = 4
	}
	return n
}

func loadReducerWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_REDUCER_WORKERS")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := runtime.NumCPU()
	if n > 4 {
		n = 4
	}
	if n < 1 {
		n = 1
	}
	return n
}

func loadCodeCallProjectionConfig(getenv func(string) string) reducer.CodeCallProjectionRunnerConfig {
	if getenv == nil {
		getenv = func(string) string { return "" }
	}

	return reducer.CodeCallProjectionRunnerConfig{
		LeaseOwner:   loadStringOrDefault(getenv, codeCallProjectionLeaseOwnerEnv, defaultCodeCallProjectionLeaseOwner),
		PollInterval: loadDurationOrDefault(getenv, codeCallProjectionPollIntervalEnv, defaultCodeCallProjectionPollInterval),
		LeaseTTL:     loadDurationOrDefault(getenv, codeCallProjectionLeaseTTLEnv, defaultCodeCallProjectionLeaseTTL),
		BatchLimit:   loadPositiveIntOrDefault(getenv, codeCallProjectionBatchLimitEnv, defaultCodeCallProjectionBatchLimit),
	}
}

func loadCodeCallEdgeWriterTuning(getenv func(string) string) (int, int) {
	if getenv == nil {
		getenv = func(string) string { return "" }
	}
	return loadPositiveIntOrDefault(getenv, codeCallEdgeBatchSizeEnv, defaultCodeCallEdgeBatchSize),
		loadPositiveIntOrDefault(getenv, codeCallEdgeGroupBatchSizeEnv, defaultCodeCallEdgeGroupBatchSize)
}

func loadGraphProjectionPhaseRepairConfig(getenv func(string) string) reducer.GraphProjectionPhaseRepairerConfig {
	if getenv == nil {
		getenv = func(string) string { return "" }
	}

	return reducer.GraphProjectionPhaseRepairerConfig{
		PollInterval: loadDurationOrDefault(getenv, graphProjectionRepairPollIntervalEnv, defaultGraphProjectionRepairPollInterval),
		BatchLimit:   loadPositiveIntOrDefault(getenv, graphProjectionRepairBatchLimitEnv, defaultGraphProjectionRepairBatchLimit),
		RetryDelay:   loadDurationOrDefault(getenv, graphProjectionRepairRetryDelayEnv, defaultGraphProjectionRepairRetryDelay),
	}
}

func loadStringOrDefault(getenv func(string) string, key string, defaultValue string) string {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	return raw
}

func loadDurationOrDefault(getenv func(string) string, key string, defaultValue time.Duration) time.Duration {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}

func loadPositiveIntOrDefault(getenv func(string) string, key string, defaultValue int) int {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}
