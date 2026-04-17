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

	defaultCodeCallProjectionPollInterval = 500 * time.Millisecond
	defaultCodeCallProjectionLeaseTTL     = 60 * time.Second
	defaultCodeCallProjectionBatchLimit   = 100
	defaultCodeCallProjectionLeaseOwner   = "code-call-projection-runner"
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
