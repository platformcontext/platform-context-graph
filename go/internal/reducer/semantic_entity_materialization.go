package reducer

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

// SemanticEntityRow holds one canonical semantic-entity materialization row.
type SemanticEntityRow struct {
	RepoID       string
	EntityID     string
	EntityType   string
	EntityName   string
	FilePath     string
	RelativePath string
	Language     string
	StartLine    int
	EndLine      int
	Metadata     map[string]any
}

// SemanticEntityWrite captures one canonical semantic-entity write request.
type SemanticEntityWrite struct {
	RepoIDs []string
	Rows    []SemanticEntityRow
}

// SemanticEntityWriteResult captures the canonical semantic-entity write outcome.
type SemanticEntityWriteResult struct {
	CanonicalWrites int
}

// SemanticEntityWriter persists Annotation, Typedef, TypeAlias, Component,
// ImplBlock, Protocol, ProtocolImplementation, and JavaScript callable
// Function semantic nodes into Neo4j.
type SemanticEntityWriter interface {
	WriteSemanticEntities(context.Context, SemanticEntityWrite) (SemanticEntityWriteResult, error)
}

// SemanticEntityMaterializationHandler reduces one semantic-entity follow-up
// into canonical graph writes. It loads parser facts, extracts canonical
// semantic rows, and writes them through the Neo4j adapter.
type SemanticEntityMaterializationHandler struct {
	FactLoader FactLoader
	Writer     SemanticEntityWriter
}

// Handle executes the semantic-entity materialization path.
func (h SemanticEntityMaterializationHandler) Handle(
	ctx context.Context,
	intent Intent,
) (Result, error) {
	if intent.Domain != DomainSemanticEntityMaterialization {
		return Result{}, fmt.Errorf(
			"semantic entity materialization handler does not accept domain %q",
			intent.Domain,
		)
	}
	if h.FactLoader == nil {
		return Result{}, fmt.Errorf("semantic entity materialization fact loader is required")
	}
	if h.Writer == nil {
		return Result{}, fmt.Errorf("semantic entity materialization writer is required")
	}

	envelopes, err := h.FactLoader.ListFacts(ctx, intent.ScopeID, intent.GenerationID)
	if err != nil {
		return Result{}, fmt.Errorf("load facts for semantic entity materialization: %w", err)
	}

	repoIDs, rows := ExtractSemanticEntityRows(envelopes)
	if len(repoIDs) == 0 && len(rows) == 0 {
		return Result{
			IntentID:        intent.IntentID,
			Domain:          DomainSemanticEntityMaterialization,
			Status:          ResultStatusSucceeded,
			EvidenceSummary: "no semantic entities found",
		}, nil
	}

	writeResult, err := h.Writer.WriteSemanticEntities(ctx, SemanticEntityWrite{
		RepoIDs: repoIDs,
		Rows:    rows,
	})
	if err != nil {
		return Result{}, fmt.Errorf("write semantic entities: %w", err)
	}

	summary := fmt.Sprintf("materialized %d semantic entities across %d repositories", len(rows), len(repoIDs))
	if len(rows) == 0 {
		summary = fmt.Sprintf("retracted semantic entities across %d repositories", len(repoIDs))
	}

	return Result{
		IntentID:        intent.IntentID,
		Domain:          DomainSemanticEntityMaterialization,
		Status:          ResultStatusSucceeded,
		EvidenceSummary: summary,
		CanonicalWrites: writeResult.CanonicalWrites,
	}, nil
}

// ExtractSemanticEntityRows returns the touched repository IDs and canonical
// semantic rows extracted from fact envelopes.
func ExtractSemanticEntityRows(envelopes []facts.Envelope) ([]string, []SemanticEntityRow) {
	if len(envelopes) == 0 {
		return nil, nil
	}

	repoIDs := collectSemanticRepoIDs(envelopes)
	rows := make([]SemanticEntityRow, 0)
	for _, env := range envelopes {
		if env.FactKind != "content_entity" {
			continue
		}

		repoID := semanticPayloadString(env.Payload, "repo_id")
		entityType := semanticPayloadString(env.Payload, "entity_type")
		if repoID == "" || !isSemanticEntityType(env.Payload, entityType) {
			continue
		}

		entityID := semanticPayloadString(env.Payload, "entity_id")
		entityName := semanticPayloadString(env.Payload, "entity_name")
		filePath := strings.TrimSpace(env.SourceRef.SourceURI)
		if entityID == "" || entityName == "" || filePath == "" {
			continue
		}

		row := SemanticEntityRow{
			RepoID:       repoID,
			EntityID:     entityID,
			EntityType:   entityType,
			EntityName:   entityName,
			FilePath:     filePath,
			RelativePath: semanticPayloadString(env.Payload, "relative_path"),
			Language:     semanticPayloadString(env.Payload, "language"),
			StartLine:    semanticPayloadInt(env.Payload, "start_line"),
			EndLine:      semanticPayloadInt(env.Payload, "end_line"),
			Metadata:     collectSemanticMetadata(env.Payload),
		}
		rows = append(rows, row)
	}

	sort.SliceStable(rows, func(i, j int) bool {
		left := rows[i]
		right := rows[j]
		if left.RepoID != right.RepoID {
			return left.RepoID < right.RepoID
		}
		if left.FilePath != right.FilePath {
			return left.FilePath < right.FilePath
		}
		if left.EntityType != right.EntityType {
			return left.EntityType < right.EntityType
		}
		if left.StartLine != right.StartLine {
			return left.StartLine < right.StartLine
		}
		return left.EntityID < right.EntityID
	})

	return repoIDs, rows
}

func collectSemanticRepoIDs(envelopes []facts.Envelope) []string {
	seen := make(map[string]struct{})
	repoIDs := make([]string, 0)
	for _, env := range envelopes {
		repoID := semanticPayloadString(env.Payload, "repo_id")
		if repoID == "" {
			continue
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		repoIDs = append(repoIDs, repoID)
	}

	sort.Strings(repoIDs)
	return repoIDs
}

func collectSemanticMetadata(payload map[string]any) map[string]any {
	metadata := cloneAnyMap(payloadMap(payload, "entity_metadata"))
	if metadata == nil {
		metadata = make(map[string]any)
	}
	for _, key := range []string{"kind", "target_kind", "type", "trait", "target", "impl_context"} {
		if value := semanticPayloadMetadataString(payload, key); value != "" {
			metadata[key] = value
		}
	}
	for _, key := range []string{"docstring", "method_kind"} {
		if value := semanticPayloadMetadataString(payload, key); value != "" {
			metadata[key] = value
		}
	}
	if len(metadata) == 0 {
		return nil
	}
	return metadata
}

func payloadMap(payload map[string]any, key string) map[string]any {
	if payload == nil {
		return nil
	}
	value, ok := payload[key]
	if !ok || value == nil {
		return nil
	}
	m, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	return m
}

func semanticPayloadString(payload map[string]any, key string) string {
	if payload == nil {
		return ""
	}
	value, ok := payload[key]
	if !ok || value == nil {
		return ""
	}
	str, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(str)
}

func semanticPayloadMetadataString(payload map[string]any, key string) string {
	if value := semanticPayloadString(payload, key); value != "" {
		return value
	}
	return semanticPayloadString(payloadMap(payload, "entity_metadata"), key)
}

func isSemanticEntityType(payload map[string]any, entityType string) bool {
	switch entityType {
	case "Annotation", "Typedef", "TypeAlias", "Component", "ImplBlock", "Protocol", "ProtocolImplementation":
		return true
	case "Function":
		return isJavaScriptCallableSemanticEntity(payload) || isRustSemanticFunction(payload)
	default:
		return false
	}
}

func isJavaScriptCallableSemanticEntity(payload map[string]any) bool {
	if semanticPayloadString(payload, "language") != "javascript" {
		return false
	}
	return semanticPayloadMetadataString(payload, "docstring") != "" || semanticPayloadMetadataString(payload, "method_kind") != ""
}

func isRustSemanticFunction(payload map[string]any) bool {
	if semanticPayloadString(payload, "language") != "rust" {
		return false
	}
	return semanticPayloadMetadataString(payload, "impl_context") != "" ||
		semanticPayloadMetadataString(payload, "trait") != "" ||
		semanticPayloadMetadataString(payload, "target") != ""
}

func semanticPayloadInt(payload map[string]any, key string) int {
	if payload == nil {
		return 0
	}
	value, ok := payload[key]
	if !ok || value == nil {
		return 0
	}
	switch typed := value.(type) {
	case int:
		return typed
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}

func cloneAnyMap(input map[string]any) map[string]any {
	if input == nil {
		return nil
	}
	cloned := make(map[string]any, len(input))
	for key, value := range input {
		cloned[key] = value
	}
	return cloned
}
