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

// SemanticEntityWriter persists Annotation, Typedef, TypeAlias,
// TypeAnnotation, Component, Module, ImplBlock, Protocol,
// ProtocolImplementation, Variable, and callable Function semantic nodes into
// Neo4j.
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
