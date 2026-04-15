package projector

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

func TestBuildSemanticEntityReducerIntentQueuesRustImplBlockSemanticEntities(t *testing.T) {
	t.Parallel()

	intent, ok := buildSemanticEntityReducerIntent(facts.Envelope{
		FactID:       "fact-1",
		ScopeID:      "scope-123",
		GenerationID: "generation-456",
		FactKind:     "content_entity",
		Payload: map[string]any{
			"entity_type":   "ImplBlock",
			"entity_id":     "impl-1",
			"entity_name":   "Point",
			"relative_path": "src/point.rs",
			"repo_id":       "repo-1",
			"language":      "rust",
			"kind":          "trait_impl",
			"trait":         "Display",
			"target":        "Point",
		},
	})
	if !ok {
		t.Fatal("buildSemanticEntityReducerIntent() ok = false, want true")
	}
	if got, want := intent.Domain, reducer.DomainSemanticEntityMaterialization; got != want {
		t.Fatalf("intent.Domain = %q, want %q", got, want)
	}
	if got, want := intent.EntityKey, "impl-1"; got != want {
		t.Fatalf("intent.EntityKey = %q, want %q", got, want)
	}
	if got, want := intent.Reason, "semantic entity follow-up for ImplBlock"; got != want {
		t.Fatalf("intent.Reason = %q, want %q", got, want)
	}
}
