//go:build !nolocalllm

package main

import (
	"context"
	"fmt"

	"github.com/platformcontext/platform-context-graph/go/internal/pcglocal"
)

// embeddedLocalNornicDBAvailable reports whether this PCG binary contains the
// NornicDB library-mode runtime. Plain builds keep the process fallback because
// current NornicDB library imports require the no-local-LLM build tag.
func embeddedLocalNornicDBAvailable() bool {
	return false
}

// startEmbeddedLocalNornicDB returns actionable guidance when the caller asks a
// plain PCG build to use the library-mode runtime.
func startEmbeddedLocalNornicDB(ctx context.Context, layout pcglocal.Layout) (*managedLocalGraph, error) {
	return nil, fmt.Errorf("embedded NornicDB is not available in this PCG build; rebuild with -tags nolocalllm or set %s=process", localNornicDBRuntimeModeEnv)
}
