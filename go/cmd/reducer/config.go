package main

import (
	"runtime"
	"strconv"
	"strings"

	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
)

const (
	reducerRetryDelayEnv  = "PCG_REDUCER_RETRY_DELAY"
	reducerMaxAttemptsEnv = "PCG_REDUCER_MAX_ATTEMPTS"
)

func loadReducerQueueConfig(getenv func(string) string) (runtimecfg.RetryPolicyConfig, error) {
	if getenv == nil {
		getenv = func(string) string { return "" }
	}

	return runtimecfg.LoadRetryPolicyConfig(getenv, "REDUCER")
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
