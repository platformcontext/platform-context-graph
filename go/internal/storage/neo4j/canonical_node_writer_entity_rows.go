package neo4j

import "github.com/platformcontext/platform-context-graph/go/internal/projector"

func canonicalEntityRowsByLabel(mat projector.CanonicalMaterialization) map[string][]map[string]any {
	if len(mat.Entities) == 0 {
		return nil
	}

	byLabel := make(map[string][]map[string]any, len(mat.Entities))
	for _, entity := range mat.Entities {
		row := map[string]any{
			"entity_id":     entity.EntityID,
			"generation_id": mat.GenerationID,
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

func canonicalEntityRowsByLabelWithFile(mat projector.CanonicalMaterialization) map[string][]map[string]any {
	if len(mat.Entities) == 0 {
		return nil
	}

	byLabel := make(map[string][]map[string]any, len(mat.Entities))
	for _, entity := range mat.Entities {
		row := map[string]any{
			"entity_id":     entity.EntityID,
			"file_path":     entity.FilePath,
			"generation_id": mat.GenerationID,
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

func canonicalEntityRowsByLabelAndFile(mat projector.CanonicalMaterialization) map[string]map[string][]map[string]any {
	if len(mat.Entities) == 0 {
		return nil
	}

	byLabel := make(map[string]map[string][]map[string]any, len(mat.Entities))
	for _, entity := range mat.Entities {
		byFile := byLabel[entity.Label]
		if byFile == nil {
			byFile = make(map[string][]map[string]any)
			byLabel[entity.Label] = byFile
		}
		row := canonicalEntityBaseRow(entity, mat.ScopeID, mat.GenerationID)
		row["props"] = canonicalEntityProperties(
			entity,
			mat.ScopeID,
			mat.GenerationID,
		)
		if dynamicProps := canonicalEntityDynamicProperties(entity); len(dynamicProps) > 0 {
			row["dynamic_props"] = dynamicProps
		}
		byFile[entity.FilePath] = append(byFile[entity.FilePath], row)
	}

	return byLabel
}

// canonicalEntityBaseRow keeps fixed canonical properties addressable as row
// fields so NornicDB can use its explicit SET batch path.
func canonicalEntityBaseRow(entity projector.EntityRow, scopeID string, generationID string) map[string]any {
	return map[string]any{
		"entity_id":     entity.EntityID,
		"name":          entity.EntityName,
		"path":          entity.FilePath,
		"relative_path": entity.RelativePath,
		"start_line":    entity.StartLine,
		"end_line":      entity.EndLine,
		"repo_id":       entity.RepoID,
		"language":      entity.Language,
		"scope_id":      scopeID,
		"generation_id": generationID,
	}
}

// canonicalEntityDynamicProperties returns parser metadata that cannot be
// encoded in the fixed canonical SET list without changing graph truth.
func canonicalEntityDynamicProperties(entity projector.EntityRow) map[string]any {
	row := map[string]any{
		"entity_metadata": entity.Metadata,
		"language":        entity.Language,
		"label":           entity.Label,
	}

	result := map[string]any{}
	if metadata := canonicalEntityMetadataProperties(row); len(metadata) > 0 {
		for key, value := range metadata {
			result[key] = value
		}
	}
	if metadata := canonicalTypeScriptClassFamilyMetadata(row); len(metadata) > 0 {
		for key, value := range metadata {
			result[key] = value
		}
	}
	if len(result) == 0 {
		return nil
	}
	return result
}

// canonicalEntityRowHasDynamicProperties identifies rows that must keep the
// map-property fallback to preserve dynamic parser metadata.
func canonicalEntityRowHasDynamicProperties(row map[string]any) bool {
	dynamic, ok := row["dynamic_props"].(map[string]any)
	return ok && len(dynamic) > 0
}
