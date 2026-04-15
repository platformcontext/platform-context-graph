package projector

import (
	"fmt"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/content"
	"github.com/platformcontext/platform-context-graph/go/internal/facts"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

var semanticEntityReducerTypes = map[string]struct{}{
	"Annotation":             {},
	"Typedef":                {},
	"TypeAlias":              {},
	"Component":              {},
	"ImplBlock":              {},
	"Protocol":               {},
	"ProtocolImplementation": {},
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
		if !isJavaScriptCallableSemanticEntity(fact.Payload, entityType) && !isPythonCallableSemanticEntity(fact.Payload, entityType) {
			return ReducerIntent{}, false
		}
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

func isJavaScriptCallableSemanticEntity(payload map[string]any, entityType string) bool {
	if entityType != "Function" {
		return false
	}
	if payloadMetadataString(payload, "language") != "javascript" {
		return false
	}
	return payloadMetadataString(payload, "docstring") != "" || payloadMetadataString(payload, "method_kind") != ""
}

func isPythonCallableSemanticEntity(payload map[string]any, entityType string) bool {
	if entityType != "Function" {
		return false
	}
	if payloadMetadataString(payload, "language") != "python" {
		return false
	}
	if payloadMetadataString(payload, "semantic_kind") == "lambda" {
		return true
	}
	if payloadMetadataBool(payload, "async") {
		return true
	}
	return len(payloadMetadataStringSlice(payload, "decorators")) > 0
}

func payloadMetadataString(payload map[string]any, key string) string {
	if value, ok := payloadString(payload, key); ok {
		return value
	}
	raw, ok := payload["entity_metadata"]
	if !ok || raw == nil {
		return ""
	}
	metadata, ok := raw.(map[string]any)
	if !ok {
		return ""
	}
	value, ok := payloadString(metadata, key)
	if !ok {
		return ""
	}
	return value
}

func payloadMetadataStringSlice(payload map[string]any, key string) []string {
	if values := payloadStringSlice(payload, key); len(values) > 0 {
		return values
	}
	raw, ok := payload["entity_metadata"]
	if !ok || raw == nil {
		return nil
	}
	metadata, ok := raw.(map[string]any)
	if !ok {
		return nil
	}
	return payloadStringSlice(metadata, key)
}

func payloadMetadataBool(payload map[string]any, key string) bool {
	if value, ok := payload[key]; ok {
		if typed, ok := value.(bool); ok {
			return typed
		}
	}
	raw, ok := payload["entity_metadata"]
	if !ok || raw == nil {
		return false
	}
	metadata, ok := raw.(map[string]any)
	if !ok {
		return false
	}
	value, ok := metadata[key]
	if !ok {
		return false
	}
	typed, ok := value.(bool)
	return ok && typed
}

func payloadStringSlice(payload map[string]any, key string) []string {
	if len(payload) == 0 {
		return nil
	}
	value, ok := payload[key]
	if !ok || value == nil {
		return nil
	}
	switch typed := value.(type) {
	case []string:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				out = append(out, trimmed)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			text, ok := item.(string)
			if !ok {
				continue
			}
			if trimmed := strings.TrimSpace(text); trimmed != "" {
				out = append(out, trimmed)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}
