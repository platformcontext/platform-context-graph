package tfstate

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
	if got, want := len(contract.Checkpoints), 2; got != want {
		t.Fatalf("len(Checkpoints) = %d, want %d", got, want)
	}
	if got, want := contract.Checkpoints[0].Keyspace, reducer.GraphProjectionKeyspaceTerraformResourceUID; got != want {
		t.Fatalf("Checkpoints[0].Keyspace = %q, want %q", got, want)
	}
	if got, want := contract.Checkpoints[1].Keyspace, reducer.GraphProjectionKeyspaceTerraformModuleUID; got != want {
		t.Fatalf("Checkpoints[1].Keyspace = %q, want %q", got, want)
	}
}
