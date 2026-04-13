package main

import (
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

const projectorRetryOnceScopeGenerationEnv = "PCG_PROJECTOR_RETRY_ONCE_SCOPE_GENERATION"

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
