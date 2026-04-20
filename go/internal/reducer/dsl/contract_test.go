package dsl

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestDefaultRuntimeContract(t *testing.T) {
	t.Parallel()

	contract := DefaultRuntimeContract()
	if err := contract.Validate(); err != nil {
		t.Fatalf("Validate() error = %v, want nil", err)
	}
	if got, want := contract.Checkpoints[0].Phase, reducer.GraphProjectionPhaseCrossSourceAnchorReady; got != want {
		t.Fatalf("Checkpoints[0].Phase = %q, want %q", got, want)
	}
	if got, want := contract.Checkpoints[len(contract.Checkpoints)-1].Phase, reducer.GraphProjectionPhaseWorkloadMaterialization; got != want {
		t.Fatalf("last checkpoint phase = %q, want %q", got, want)
	}
}
