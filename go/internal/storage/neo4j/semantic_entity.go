package neo4j

import (
	"context"
	"fmt"
	"sort"

	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

const (
	semanticEntityEvidenceSource = "parser/semantic-entities"

	semanticAnnotationUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Annotation {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.kind = row.kind,
    n.target_kind = row.target_kind,
    n.semantic_kind = row.entity_type,
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticTypedefUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Typedef {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.type = row.type,
    n.semantic_kind = row.entity_type,
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticTypeAliasUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:TypeAlias {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.type_alias_kind = row.type_alias_kind,
    n.type_parameters = row.type_parameters,
    n.semantic_kind = row.entity_type,
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticComponentUpsertCypher = `UNWIND $rows AS row
MATCH (f:File {path: row.file_path})
MERGE (n:Component {uid: row.entity_id})
SET n.id = row.entity_id,
    n.name = row.entity_name,
    n.path = row.file_path,
    n.relative_path = row.relative_path,
    n.line_number = row.start_line,
    n.start_line = row.start_line,
    n.end_line = row.end_line,
    n.repo_id = row.repo_id,
    n.language = row.language,
    n.lang = row.language,
    n.framework = row.framework,
    n.jsx_fragment_shorthand = row.jsx_fragment_shorthand,
    n.component_type_assertion = row.component_type_assertion,
    n.semantic_kind = row.entity_type,
    n.evidence_source = row.evidence_source
MERGE (f)-[:CONTAINS]->(n)`

	semanticEntityRetractCypher = `MATCH (n:Annotation|Typedef|TypeAlias|Component)
WHERE n.repo_id IN $repo_ids
  AND n.evidence_source = $evidence_source
DETACH DELETE n`
)

// SemanticEntityWriter writes Annotation, Typedef, TypeAlias, and Component
// semantic nodes into Neo4j.
type SemanticEntityWriter struct {
	executor  Executor
	BatchSize int
}

// NewSemanticEntityWriter returns a semantic-entity writer backed by the given Executor.
func NewSemanticEntityWriter(executor Executor, batchSize int) *SemanticEntityWriter {
	return &SemanticEntityWriter{executor: executor, BatchSize: batchSize}
}

func (w *SemanticEntityWriter) batchSize() int {
	if w.BatchSize <= 0 {
		return DefaultBatchSize
	}
	return w.BatchSize
}

// WriteSemanticEntities retracts stale Annotation and Typedef nodes for the
// touched repositories and upserts the current rows.
func (w *SemanticEntityWriter) WriteSemanticEntities(
	ctx context.Context,
	write reducer.SemanticEntityWrite,
) (reducer.SemanticEntityWriteResult, error) {
	if len(write.RepoIDs) == 0 && len(write.Rows) == 0 {
		return reducer.SemanticEntityWriteResult{}, nil
	}
	if w.executor == nil {
		return reducer.SemanticEntityWriteResult{}, fmt.Errorf("semantic entity writer executor is required")
	}

	repoIDs := uniqueSemanticRepoIDs(write.RepoIDs)

	if err := w.executor.Execute(ctx, Statement{
		Operation:  OperationCanonicalRetract,
		Cypher:     semanticEntityRetractCypher,
		Parameters: map[string]any{"repo_ids": repoIDs, "evidence_source": semanticEntityEvidenceSource},
	}); err != nil {
		return reducer.SemanticEntityWriteResult{}, err
	}

	rowsByLabel := map[string][]map[string]any{
		"Annotation": nil,
		"Typedef":    nil,
		"TypeAlias":  nil,
		"Component":  nil,
	}
	for _, row := range write.Rows {
		rowMap, ok := buildSemanticEntityRowMap(row)
		if !ok {
			continue
		}
		rowsByLabel[row.EntityType] = append(rowsByLabel[row.EntityType], rowMap)
	}

	writes := 0
	for _, plan := range []struct {
		label  string
		cypher string
	}{
		{label: "Annotation", cypher: semanticAnnotationUpsertCypher},
		{label: "Typedef", cypher: semanticTypedefUpsertCypher},
		{label: "TypeAlias", cypher: semanticTypeAliasUpsertCypher},
		{label: "Component", cypher: semanticComponentUpsertCypher},
	} {
		if err := w.executeSemanticEntityRows(ctx, plan.cypher, rowsByLabel[plan.label]); err != nil {
			return reducer.SemanticEntityWriteResult{}, err
		}
		writes += len(rowsByLabel[plan.label])
	}

	return reducer.SemanticEntityWriteResult{CanonicalWrites: writes}, nil
}

func (w *SemanticEntityWriter) executeSemanticEntityRows(ctx context.Context, cypher string, rows []map[string]any) error {
	if len(rows) == 0 {
		return nil
	}
	batchSize := w.batchSize()
	for start := 0; start < len(rows); start += batchSize {
		end := start + batchSize
		if end > len(rows) {
			end = len(rows)
		}
		if err := w.executor.Execute(ctx, Statement{
			Operation:  OperationCanonicalUpsert,
			Cypher:     cypher,
			Parameters: map[string]any{"rows": rows[start:end]},
		}); err != nil {
			return err
		}
	}
	return nil
}

func buildSemanticEntityRowMap(row reducer.SemanticEntityRow) (map[string]any, bool) {
	if row.RepoID == "" || row.EntityID == "" || row.EntityName == "" || row.FilePath == "" {
		return nil, false
	}
	if row.EntityType != "Annotation" && row.EntityType != "Typedef" && row.EntityType != "TypeAlias" && row.EntityType != "Component" {
		return nil, false
	}
	if row.StartLine <= 0 {
		return nil, false
	}

	rowMap := map[string]any{
		"repo_id":         row.RepoID,
		"entity_id":       row.EntityID,
		"entity_type":     row.EntityType,
		"entity_name":     row.EntityName,
		"file_path":       row.FilePath,
		"relative_path":   row.RelativePath,
		"language":        row.Language,
		"start_line":      row.StartLine,
		"end_line":        row.EndLine,
		"evidence_source": semanticEntityEvidenceSource,
	}
	if row.Metadata != nil {
		if kind := semanticMetadataString(row.Metadata, "kind"); kind != "" {
			rowMap["kind"] = kind
		}
		if targetKind := semanticMetadataString(row.Metadata, "target_kind"); targetKind != "" {
			rowMap["target_kind"] = targetKind
		}
		if typ := semanticMetadataString(row.Metadata, "type"); typ != "" {
			rowMap["type"] = typ
		}
		if aliasKind := semanticMetadataString(row.Metadata, "type_alias_kind"); aliasKind != "" {
			rowMap["type_alias_kind"] = aliasKind
		}
		if typeParameters := semanticMetadataStringSlice(row.Metadata, "type_parameters"); len(typeParameters) > 0 {
			rowMap["type_parameters"] = typeParameters
		}
		if framework := semanticMetadataString(row.Metadata, "framework"); framework != "" {
			rowMap["framework"] = framework
		}
		if jsxFragment := semanticMetadataBool(row.Metadata, "jsx_fragment_shorthand"); jsxFragment != nil {
			rowMap["jsx_fragment_shorthand"] = *jsxFragment
		}
		if componentAssertion := semanticMetadataString(row.Metadata, "component_type_assertion"); componentAssertion != "" {
			rowMap["component_type_assertion"] = componentAssertion
		}
	}
	return rowMap, true
}

func semanticMetadataString(metadata map[string]any, key string) string {
	if metadata == nil {
		return ""
	}
	value, ok := metadata[key]
	if !ok || value == nil {
		return ""
	}
	str, ok := value.(string)
	if !ok {
		return ""
	}
	return str
}

func semanticMetadataStringSlice(metadata map[string]any, key string) []string {
	if metadata == nil {
		return nil
	}
	value, ok := metadata[key]
	if !ok || value == nil {
		return nil
	}
	switch typed := value.(type) {
	case []string:
		if len(typed) == 0 {
			return nil
		}
		return append([]string(nil), typed...)
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			str, ok := item.(string)
			if !ok || str == "" {
				continue
			}
			out = append(out, str)
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}

func semanticMetadataBool(metadata map[string]any, key string) *bool {
	if metadata == nil {
		return nil
	}
	value, ok := metadata[key]
	if !ok || value == nil {
		return nil
	}
	switch typed := value.(type) {
	case bool:
		v := typed
		return &v
	default:
		return nil
	}
}

func uniqueSemanticRepoIDs(repoIDs []string) []string {
	seen := make(map[string]struct{})
	unique := make([]string, 0, len(repoIDs))
	for _, repoID := range repoIDs {
		if repoID == "" {
			continue
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		unique = append(unique, repoID)
	}
	sort.Strings(unique)
	return unique
}
