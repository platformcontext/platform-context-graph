package tags

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
	if got, want := contract.CanonicalKeyspaces[0], reducer.GraphProjectionKeyspaceCloudResourceUID; got != want {
		t.Fatalf("CanonicalKeyspaces[0] = %q, want %q", got, want)
	}
}
