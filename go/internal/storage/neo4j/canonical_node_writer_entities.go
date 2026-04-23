package neo4j

import (
	"fmt"
	"sort"

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
			"properties": canonicalEntityProperties(
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
		cypher := fmt.Sprintf(canonicalNodeEntityUpsertTemplate, label)
		for _, row := range byLabel[label] {
			stmts = append(stmts, Statement{
				Operation:  OperationCanonicalUpsert,
				Cypher:     cypher,
				Parameters: row,
			})
		}
	}

	return stmts
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

// buildEntityContainmentStatements links files to already-upserted entities in
// a separate phase so the entity upsert hot path stays index-friendly.
func (w *CanonicalNodeWriter) buildEntityContainmentStatements(mat projector.CanonicalMaterialization) []Statement {
	byLabel := canonicalEntityContainmentRowsByLabel(mat)
	if len(byLabel) == 0 {
		return nil
	}

	var stmts []Statement
	for _, label := range sortedCanonicalEntityLabels(byLabel) {
		cypher := fmt.Sprintf(canonicalNodeEntityContainmentEdgeTemplate, label)
		for _, row := range byLabel[label] {
			stmts = append(stmts, Statement{
				Operation:  OperationCanonicalUpsert,
				Cypher:     cypher,
				Parameters: row,
			})
		}
	}

	return stmts
}

func canonicalEntityContainmentRowsByLabel(mat projector.CanonicalMaterialization) map[string][]map[string]any {
	if len(mat.Entities) == 0 {
		return nil
	}

	byLabel := make(map[string][]map[string]any, len(mat.Entities))
	for _, entity := range mat.Entities {
		byLabel[entity.Label] = append(byLabel[entity.Label], map[string]any{
			"file_path": entity.FilePath,
			"entity_id": entity.EntityID,
		})
	}

	return byLabel
}
