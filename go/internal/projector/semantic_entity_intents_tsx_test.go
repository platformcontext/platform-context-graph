package projector

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestBuildSemanticEntityReducerIntentQueuesTSXFunctionFragmentSemanticEntities(t *testing.T) {
	t.Parallel()

	intent, ok := buildSemanticEntityReducerIntent(facts.Envelope{
		FactID:       "fact-tsx-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		FactKind:     "content_entity",
		Payload: map[string]any{
			"entity_type":            "Function",
			"entity_id":              "function-tsx-1",
			"entity_name":            "Screen",
			"relative_path":          "src/Screen.tsx",
			"repo_id":                "repo-1",
			"language":               "tsx",
			"jsx_fragment_shorthand": true,
		},
	})
	if !ok {
		t.Fatal("buildSemanticEntityReducerIntent() ok = false, want true")
	}
	if got, want := intent.Domain, reducer.DomainSemanticEntityMaterialization; got != want {
		t.Fatalf("intent.Domain = %q, want %q", got, want)
	}
	if got, want := intent.EntityKey, "function-tsx-1"; got != want {
		t.Fatalf("intent.EntityKey = %q, want %q", got, want)
	}
}
