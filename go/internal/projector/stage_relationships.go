package projector

import (
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/graph"
)

// RelationshipStageResult captures the output of the relationship projection
// stage.
type RelationshipStageResult struct {
	GraphRecords []graph.Record
	Intents      []ReducerIntent
}

// ProjectRelationshipStage projects relationship-bearing facts into graph
// records and reducer intents. Relationship facts are any facts that carry
// a graph_id with relationship semantics or a reducer_domain payload key.
//
// In the Python codebase this stage rebuilds imports_map and creates function
// call/inheritance links. In Go, those relationships arrive as pre-built fact
// payloads with graph_id and reducer_domain keys, so this stage filters and
// builds records from them.
func ProjectRelationshipStage(envelopes []facts.Envelope) RelationshipStageResult {
	result := RelationshipStageResult{}

	// Process all facts (not just one kind) for relationship records, since
	// relationship graph records and reducer intents can come from any fact
	// kind that carries the right payload keys.
	seen := make(map[string]struct{}, len(envelopes))
	for i := range envelopes {
		if _, ok := seen[envelopes[i].FactID]; ok {
			continue
		}
		seen[envelopes[i].FactID] = struct{}{}

		if record, ok := buildGraphRecord(envelopes[i]); ok {
			result.GraphRecords = append(result.GraphRecords, record)
		}
		if intent, ok := buildReducerIntent(envelopes[i]); ok {
			result.Intents = append(result.Intents, intent)
		}
	}

	return result
}
