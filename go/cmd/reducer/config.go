package main

import (
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
