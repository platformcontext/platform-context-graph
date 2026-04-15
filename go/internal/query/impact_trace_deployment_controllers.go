package query

import (
	"context"
	"fmt"
	"slices"
)

var controllerEntityTypes = map[string]string{
	"ArgoCDApplication":    "argocd_application",
	"ArgoCDApplicationSet": "argocd_applicationset",
}

func (h *ImpactHandler) fetchControllerEntities(
	ctx context.Context,
	deploymentSources []map[string]any,
) ([]map[string]any, error) {
	if h == nil || h.Content == nil || len(deploymentSources) == 0 {
		return nil, nil
	}

	repoIDs := uniqueNonEmptyRepoIDs(deploymentSources)
	controllers := make([]map[string]any, 0, len(repoIDs))
	for _, repoID := range repoIDs {
		entities, err := h.Content.ListRepoEntities(ctx, repoID, 500)
		if err != nil {
			return nil, fmt.Errorf("list controller entities for %s: %w", repoID, err)
		}
		for _, entity := range entities {
			controllerKind, ok := controllerEntityTypes[entity.EntityType]
			if !ok {
				continue
			}
			controllers = append(controllers, map[string]any{
				"entity_id":              entity.EntityID,
				"entity_type":            entity.EntityType,
				"entity_name":            entity.EntityName,
				"controller_kind":        controllerKind,
				"repo_id":                entity.RepoID,
				"relative_path":          entity.RelativePath,
				"source_repo":            metadataNonEmptyStringValue(entity.Metadata, "source_repo"),
				"source_path":            metadataNonEmptyStringValue(entity.Metadata, "source_path"),
				"generator_source_repos": slices.Clone(metadataStringSlice(entity.Metadata, "generator_source_repos")),
				"generator_source_paths": slices.Clone(metadataStringSlice(entity.Metadata, "generator_source_paths")),
				"template_source_repos":  slices.Clone(metadataStringSlice(entity.Metadata, "template_source_repos")),
				"template_source_paths":  slices.Clone(metadataStringSlice(entity.Metadata, "template_source_paths")),
				"dest_server":            metadataNonEmptyStringValue(entity.Metadata, "dest_server"),
				"dest_namespace":         metadataNonEmptyStringValue(entity.Metadata, "dest_namespace"),
			})
		}
	}
	return controllers, nil
}

func buildControllerOverview(
	platforms []string,
	platformKinds []string,
	controllerEntities []map[string]any,
) map[string]any {
	overview := map[string]any{
		"controller_count": len(platforms),
		"controllers":      platforms,
		"controller_kinds": platformKinds,
	}
	if len(controllerEntities) > 0 {
		overview["entities"] = controllerEntities
	}
	return overview
}

func metadataNonEmptyStringValue(metadata map[string]any, key string) string {
	value, _ := metadataNonEmptyString(metadata, key)
	return value
}

func uniqueNonEmptyRepoIDs(sources []map[string]any) []string {
	if len(sources) == 0 {
		return nil
	}
	seen := make(map[string]struct{}, len(sources))
	repoIDs := make([]string, 0, len(sources))
	for _, source := range sources {
		repoID := safeStr(source, "repo_id")
		if repoID == "" {
			continue
		}
		if _, ok := seen[repoID]; ok {
			continue
		}
		seen[repoID] = struct{}{}
		repoIDs = append(repoIDs, repoID)
	}
	return repoIDs
}
