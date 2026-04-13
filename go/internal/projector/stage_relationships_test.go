package projector

import (
	"testing"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func TestRelationshipStageBuildsGraphRecords(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactID:   "r-1",
			FactKind: "FileObserved",
			Payload: map[string]any{
				"graph_id":   "file:src/main.py",
				"graph_kind": "File",
			},
		},
	}

	result := ProjectRelationshipStage(envelopes)
	if len(result.GraphRecords) != 1 {
		t.Fatalf("GraphRecords len = %d, want 1", len(result.GraphRecords))
	}
	if result.GraphRecords[0].RecordID != "file:src/main.py" {
		t.Errorf("RecordID = %q", result.GraphRecords[0].RecordID)
	}
}

func TestRelationshipStageBuildsReducerIntents(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{
			FactID:       "i-1",
			FactKind:     "FileObserved",
			ScopeID:      "scope-1",
			GenerationID: "gen-1",
			Payload: map[string]any{
				"reducer_domain": "data_lineage",
				"entity_key":     "repo:r1",
				"reason":         "import detected",
			},
		},
	}

	result := ProjectRelationshipStage(envelopes)
	if len(result.Intents) != 1 {
		t.Fatalf("Intents len = %d, want 1", len(result.Intents))
	}
	if result.Intents[0].EntityKey != "repo:r1" {
		t.Errorf("EntityKey = %q", result.Intents[0].EntityKey)
	}
}

func TestRelationshipStageDeduplicates(t *testing.T) {
	t.Parallel()

	envelopes := []facts.Envelope{
		{FactID: "r-1", FactKind: "FileObserved", Payload: map[string]any{"graph_id": "file:x", "graph_kind": "File"}},
		{FactID: "r-1", FactKind: "FileObserved", Payload: map[string]any{"graph_id": "file:x", "graph_kind": "File"}},
	}

	result := ProjectRelationshipStage(envelopes)
	if len(result.GraphRecords) != 1 {
		t.Errorf("GraphRecords len = %d, want 1 (deduped)", len(result.GraphRecords))
	}
}
