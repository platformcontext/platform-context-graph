package postgres

import (
	"strings"
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

func TestReducerWorkItemIDDeterministic(t *testing.T) {
	t.Parallel()
	intent := projector.ReducerIntent{
		ScopeID:      "scope-1",
		GenerationID: "gen-1",
		Domain:       "workload_identity",
		EntityKey:    "entity-1",
	}
	id1 := reducerWorkItemID(intent)
	id2 := reducerWorkItemID(intent)
	if id1 != id2 {
		t.Fatalf("expected deterministic ID, got %q and %q", id1, id2)
	}
	if !strings.HasPrefix(id1, "reducer_") {
		t.Fatalf("expected prefix 'reducer_', got %q", id1)
	}
}

func TestReducerWorkItemIDSanitizesSpecialChars(t *testing.T) {
	t.Parallel()
	intent := projector.ReducerIntent{
		ScopeID:      "org/repo",
		GenerationID: "gen:1",
		Domain:       "workload_identity",
		EntityKey:    "entity/key:value",
	}
	id := reducerWorkItemID(intent)
	if strings.Contains(id, "/") || strings.Contains(id, ":") {
		t.Fatalf("ID contains unsanitized chars: %q", id)
	}
}
