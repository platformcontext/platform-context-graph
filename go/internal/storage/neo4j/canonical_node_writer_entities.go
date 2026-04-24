package neo4j

import (
	"fmt"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/projector"
)

func canonicalEntityRowsByLabel(mat projector.CanonicalMaterialization) map[string][]map[string]any {
	if len(mat.Entities) == 0 {
		return nil
	}

	byLabel := make(map[string][]map[string]any, len(mat.Entities))
	for _, entity := range mat.Entities {
		row := map[string]any{
			"entity_id": entity.EntityID,
			"file_path": entity.FilePath,
			"props": canonicalEntityProperties(
				entity,
				mat.ScopeID,
				mat.GenerationID,
			),
		}
		byLabel[entity.Label] = append(byLabel[entity.Label], row)
	}

	return byLabel
}

func sortedCanonicalEntityLabels(byLabel map[string][]map[string]any) []string {
	labels := make([]string, 0, len(byLabel))
	for label := range byLabel {
		labels = append(labels, label)
	}
	sort.Strings(labels)
	return labels
}

// buildEntityStatements writes entity nodes first so backend-specific edge
// creation can happen in a later, separately timed phase.
func (w *CanonicalNodeWriter) buildEntityStatements(mat projector.CanonicalMaterialization) []Statement {
	byLabel := canonicalEntityRowsByLabel(mat)
	if len(byLabel) == 0 {
		return nil
	}

	var stmts []Statement
	for _, label := range sortedCanonicalEntityLabels(byLabel) {
		rows := byLabel[label]
		batchSize := w.batchSize
		if batchSize <= 0 {
			batchSize = DefaultBatchSize
		}
		batchRows := make([]map[string]any, 0, batchSize)
		flushBatch := func() {
			if len(batchRows) == 0 {
				return
			}
			statementSummary := fmt.Sprintf(
				"label=%s rows=%d first_id=%v last_id=%v",
				label,
				len(batchRows),
				batchRows[0]["entity_id"],
				batchRows[len(batchRows)-1]["entity_id"],
			)
			stmts = append(stmts, Statement{
				Operation: OperationCanonicalUpsert,
				Cypher:    fmt.Sprintf(canonicalNodeEntityUpsertTemplate, label),
				Parameters: map[string]any{
					"rows":                   append([]map[string]any(nil), batchRows...),
					"_pcg_statement_summary": statementSummary,
				},
			})
			batchRows = batchRows[:0]
		}
		for _, row := range rows {
			if canonicalEntityRowNeedsSingletonFallback(row) {
				flushBatch()
				stmts = append(stmts, Statement{
					Operation: OperationCanonicalUpsert,
					Cypher:    fmt.Sprintf(canonicalNodeEntitySingletonUpsertTemplate, label),
					Parameters: map[string]any{
						"file_path": row["file_path"],
						"entity_id": row["entity_id"],
						"props":     row["props"],
						"_pcg_statement_summary": fmt.Sprintf(
							"label=%s rows=1 entity_id=%v fallback=singleton_parameterized",
							label,
							row["entity_id"],
						),
					},
				})
				continue
			}
			batchRows = append(batchRows, row)
			if len(batchRows) >= batchSize {
				flushBatch()
			}
		}
		flushBatch()
	}

	return stmts
}

func canonicalEntityRowNeedsSingletonFallback(row map[string]any) bool {
	return canonicalEntityValueContainsSubstring(row, "shortestpath") ||
		canonicalEntityValueContainsSubstring(row, "allshortestpaths")
}

func canonicalEntityValueContainsSubstring(value any, needle string) bool {
	switch typed := value.(type) {
	case string:
		return strings.Contains(strings.ToLower(typed), needle)
	case []string:
		for _, item := range typed {
			if canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	case map[string]any:
		for key, item := range typed {
			if canonicalEntityValueContainsSubstring(key, needle) || canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	}
	return false
}

func canonicalEntityProperties(
	entity projector.EntityRow,
	scopeID string,
	generationID string,
) map[string]any {
	properties := map[string]any{
		"id":              entity.EntityID,
		"name":            entity.EntityName,
		"path":            entity.FilePath,
		"relative_path":   entity.RelativePath,
		"line_number":     entity.StartLine,
		"start_line":      entity.StartLine,
		"end_line":        entity.EndLine,
		"repo_id":         entity.RepoID,
		"language":        entity.Language,
		"lang":            entity.Language,
		"scope_id":        scopeID,
		"generation_id":   generationID,
		"evidence_source": "projector/canonical",
	}

	row := map[string]any{
		"entity_metadata": entity.Metadata,
		"language":        entity.Language,
		"label":           entity.Label,
	}
	if metadata := canonicalTypeScriptClassFamilyMetadata(row); len(metadata) > 0 {
		for key, value := range metadata {
			properties[key] = value
		}
	}

	return properties
}

// buildEntityContainmentStatements returns nil because canonical entity batches
// now merge their CONTAINS edge in the entity upsert statement itself.
func (w *CanonicalNodeWriter) buildEntityContainmentStatements(mat projector.CanonicalMaterialization) []Statement {
	_ = mat
	return nil
}
