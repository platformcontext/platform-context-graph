package main

import (
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
	runtimecfg "github.com/platformcontext/platform-context-graph/go/internal/runtime"
)

const (
	projectorRetryOnceScopeGenerationEnv = "PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION"
	projectorClaimOrderEnv               = "PCG_PROJECTOR_CLAIM_ORDER"
)

func loadProjectorRetryInjector(getenv func(string) string) (projector.RetryInjector, error) {
	if getenv == nil {
		return nil, nil
	}

	raw := strings.TrimSpace(getenv(projectorRetryOnceScopeGenerationEnv))
	if raw == "" {
		return nil, nil
	}

	return projector.NewRetryOnceInjector(raw)
}

func loadProjectorRetryPolicy(getenv func(string) string) (runtimecfg.RetryPolicyConfig, error) {
	return runtimecfg.LoadRetryPolicyConfig(getenv, "PROJECTOR")
}

func loadProjectorPreferLargeGenerationsFirst(getenv func(string) string) bool {
	if getenv == nil {
		return false
	}
	switch strings.ToLower(strings.TrimSpace(getenv(projectorClaimOrderEnv))) {
	case "size_desc", "large_first":
		return true
	default:
		return false
	}
}
