package projector

import (
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

var semanticEntityReducerTypes = map[string]struct{}{
	"Annotation": {},
	"Typedef":    {},
	"TypeAlias":  {},
	"Component":  {},
}

func buildSemanticEntityReducerIntent(fact facts.Envelope) (ReducerIntent, bool) {
	if fact.FactKind != "content_entity" {
		return ReducerIntent{}, false
	}

	entityType, ok := payloadString(fact.Payload, "entity_type")
	if !ok {
		return ReducerIntent{}, false
	}
	if _, ok := semanticEntityReducerTypes[entityType]; !ok {
		return ReducerIntent{}, false
	}

	repoID, _ := payloadString(fact.Payload, "repo_id")
	relativePath, _ := payloadString(fact.Payload, "relative_path")
	if relativePath == "" {
		relativePath = strings.TrimSpace(fact.SourceRef.SourceURI)
	}
	entityName, _ := payloadString(fact.Payload, "entity_name")
	startLine, _ := payloadInt(fact.Payload, "start_line")

	entityID, _ := payloadString(fact.Payload, "entity_id")
	if entityID == "" {
		entityID = content.CanonicalEntityID(repoID, relativePath, entityType, entityName, startLine)
	}
	if entityID == "" {
		return ReducerIntent{}, false
	}

	return ReducerIntent{
		ScopeID:      fact.ScopeID,
		GenerationID: fact.GenerationID,
		Domain:       reducer.DomainSemanticEntityMaterialization,
		EntityKey:    entityID,
		Reason:       fmt.Sprintf("semantic entity follow-up for %s", entityType),
		FactID:       fact.FactID,
		SourceSystem: fact.SourceRef.SourceSystem,
	}, true
}
