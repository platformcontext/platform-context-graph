package query

import (
	"context"
	"fmt"
	"strings"
)

const contentRelationshipLimit = 20

type contentRelationshipSet struct {
	incoming []map[string]any
	outgoing []map[string]any
}

func buildContentRelationshipSet(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) (contentRelationshipSet, error) {
	if reader == nil {
		return contentRelationshipSet{}, nil
	}

	outgoing, err := buildOutgoingContentRelationships(ctx, reader, entity)
	if err != nil {
		return contentRelationshipSet{}, err
	}

	incoming, err := buildIncomingContentRelationships(ctx, reader, entity)
	if err != nil {
		return contentRelationshipSet{}, err
	}

	return contentRelationshipSet{incoming: incoming, outgoing: outgoing}, nil
}

func buildOutgoingContentRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, error) {
	if relationships, ok, err := buildOutgoingK8sSelectRelationships(ctx, reader, entity); ok || err != nil {
		return relationships, err
	}

	componentNames := metadataStringSlice(entity.Metadata, "jsx_component_usage")
	if len(componentNames) == 0 {
		return nil, nil
	}

	relationships := make([]map[string]any, 0, len(componentNames))
	seen := make(map[string]struct{}, len(componentNames))
	for _, componentName := range componentNames {
		if componentName == "" {
			continue
		}
		components, err := reader.SearchEntitiesByName(ctx, entity.RepoID, "Component", componentName, contentRelationshipLimit)
		if err != nil {
			return nil, fmt.Errorf("search referenced components: %w", err)
		}
		for _, component := range components {
			if component.EntityID == entity.EntityID {
				continue
			}
			key := component.EntityID + ":" + component.EntityName
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			relationships = append(relationships, map[string]any{
				"type":        "REFERENCES",
				"target_name": component.EntityName,
				"target_id":   component.EntityID,
				"reason":      "jsx_component_usage",
			})
		}
	}

	return relationships, nil
}

func buildIncomingContentRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, error) {
	if relationships, ok, err := buildIncomingK8sSelectRelationships(ctx, reader, entity); ok || err != nil {
		return relationships, err
	}

	if entity.EntityType != "Component" || entity.EntityName == "" {
		return nil, nil
	}

	referencing, err := reader.SearchEntitiesReferencingComponent(ctx, entity.RepoID, entity.EntityName, contentRelationshipLimit)
	if err != nil {
		return nil, fmt.Errorf("search referencing entities: %w", err)
	}

	relationships := make([]map[string]any, 0, len(referencing))
	seen := make(map[string]struct{}, len(referencing))
	for _, source := range referencing {
		if source.EntityID == entity.EntityID {
			continue
		}
		key := source.EntityID + ":" + source.EntityName
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		relationships = append(relationships, map[string]any{
			"type":        "REFERENCES",
			"source_name": source.EntityName,
			"source_id":   source.EntityID,
			"reason":      "jsx_component_usage",
		})
	}

	return relationships, nil
}

func buildOutgoingK8sSelectRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, bool, error) {
	if !isK8sResourceKind(entity, "Service") || entity.EntityName == "" {
		return nil, false, nil
	}

	matches, err := reader.SearchEntitiesByName(
		ctx, entity.RepoID, "K8sResource", entity.EntityName, contentRelationshipLimit,
	)
	if err != nil {
		return nil, true, fmt.Errorf("search selected deployments: %w", err)
	}

	relationships := make([]map[string]any, 0, len(matches))
	seen := make(map[string]struct{}, len(matches))
	for _, match := range matches {
		if match.EntityID == entity.EntityID || !isK8sResourceKind(match, "Deployment") {
			continue
		}
		if !sameK8sNamespace(entity, match) {
			continue
		}
		key := match.EntityID + ":" + match.EntityName
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		relationships = append(relationships, map[string]any{
			"type":        "SELECTS",
			"target_name": match.EntityName,
			"target_id":   match.EntityID,
			"reason":      "k8s_service_name_namespace",
		})
	}

	return relationships, true, nil
}

func buildIncomingK8sSelectRelationships(
	ctx context.Context,
	reader *ContentReader,
	entity EntityContent,
) ([]map[string]any, bool, error) {
	if !isK8sResourceKind(entity, "Deployment") || entity.EntityName == "" {
		return nil, false, nil
	}

	matches, err := reader.SearchEntitiesByName(
		ctx, entity.RepoID, "K8sResource", entity.EntityName, contentRelationshipLimit,
	)
	if err != nil {
		return nil, true, fmt.Errorf("search selecting services: %w", err)
	}

	relationships := make([]map[string]any, 0, len(matches))
	seen := make(map[string]struct{}, len(matches))
	for _, match := range matches {
		if match.EntityID == entity.EntityID || !isK8sResourceKind(match, "Service") {
			continue
		}
		if !sameK8sNamespace(entity, match) {
			continue
		}
		key := match.EntityID + ":" + match.EntityName
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		relationships = append(relationships, map[string]any{
			"type":        "SELECTS",
			"source_name": match.EntityName,
			"source_id":   match.EntityID,
			"reason":      "k8s_service_name_namespace",
		})
	}

	return relationships, true, nil
}

func isK8sResourceKind(entity EntityContent, kind string) bool {
	if entity.EntityType != "K8sResource" {
		return false
	}
	value, _ := entity.Metadata["kind"].(string)
	return strings.EqualFold(strings.TrimSpace(value), kind)
}

func sameK8sNamespace(left EntityContent, right EntityContent) bool {
	return strings.EqualFold(k8sNamespace(left.Metadata), k8sNamespace(right.Metadata))
}

func k8sNamespace(metadata map[string]any) string {
	value, _ := metadata["namespace"].(string)
	return strings.TrimSpace(value)
}

func metadataStringSlice(metadata map[string]any, key string) []string {
	values, ok := metadata[key]
	if !ok {
		return nil
	}

	switch typed := values.(type) {
	case []string:
		return append([]string(nil), typed...)
	case []any:
		items := make([]string, 0, len(typed))
		for _, item := range typed {
			value, ok := item.(string)
			if !ok || value == "" {
				continue
			}
			items = append(items, value)
		}
		return items
	default:
		return nil
	}
}
