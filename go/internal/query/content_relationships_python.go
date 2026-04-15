package query

import (
	"context"
	"fmt"
)

func buildOutgoingPythonMetaclassRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, bool, error) {
	metaclass, ok := metadataNonEmptyString(entity.Metadata, "metaclass")
	if entity.EntityType != "Class" || !ok || metaclass == "" {
		return nil, false, nil
	}

	matches, err := reader.SearchEntitiesByName(ctx, entity.RepoID, "Class", metaclass, contentRelationshipLimit)
	if err != nil {
		return nil, true, fmt.Errorf("search python metaclasses: %w", err)
	}

	relationships := make([]map[string]any, 0, len(matches))
	seen := make(map[string]struct{}, len(matches))
	for _, match := range matches {
		if match.EntityID == entity.EntityID || match.EntityName != metaclass {
			continue
		}
		if _, duplicate := seen[match.EntityID]; duplicate {
			continue
		}
		seen[match.EntityID] = struct{}{}
		relationships = append(relationships, map[string]any{
			"type":        "USES_METACLASS",
			"target_name": match.EntityName,
			"target_id":   match.EntityID,
			"reason":      "python_metaclass",
		})
	}

	return relationships, true, nil
}

func buildIncomingPythonMetaclassRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, bool, error) {
	if entity.EntityType != "Class" || entity.EntityName == "" {
		return nil, false, nil
	}

	matches, err := reader.SearchEntitiesByName(ctx, entity.RepoID, "Class", "", contentRelationshipLimit)
	if err != nil {
		return nil, true, fmt.Errorf("search python metaclass users: %w", err)
	}

	relationships := make([]map[string]any, 0, len(matches))
	seen := make(map[string]struct{}, len(matches))
	for _, match := range matches {
		metaclass, ok := metadataNonEmptyString(match.Metadata, "metaclass")
		if !ok || metaclass != entity.EntityName || match.EntityID == entity.EntityID {
			continue
		}
		if _, duplicate := seen[match.EntityID]; duplicate {
			continue
		}
		seen[match.EntityID] = struct{}{}
		relationships = append(relationships, map[string]any{
			"type":        "USES_METACLASS",
			"source_name": match.EntityName,
			"source_id":   match.EntityID,
			"reason":      "python_metaclass",
		})
	}

	return relationships, true, nil
}
