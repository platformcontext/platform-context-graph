package query

import (
	"context"
	"fmt"
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
			controller, ok := buildDeploymentSourceControllerEntity(entity)
			if !ok {
				continue
			}
			controllers = append(controllers, controller)
		}
	}
	return controllers, nil
}

func (h *ImpactHandler) fetchDeploymentSourceGitOps(
	ctx context.Context,
	serviceName string,
	deploymentSources []map[string]any,
) ([]map[string]any, []map[string]any, []string, error) {
	if h == nil || h.Content == nil || len(deploymentSources) == 0 {
		return nil, nil, nil, nil
	}

	repoIDs := uniqueNonEmptyRepoIDs(deploymentSources)
	entities := make([]EntityContent, 0, len(repoIDs)*8)
	for _, repoID := range repoIDs {
		rows, err := h.Content.ListRepoEntities(ctx, repoID, repositorySemanticEntityLimit)
		if err != nil {
			return nil, nil, nil, fmt.Errorf("list deployment source entities for %s: %w", repoID, err)
		}
		entities = append(entities, rows...)
	}

	controllers := selectRelevantDeploymentSourceControllers(serviceName, deploymentSources, entities)
	k8sResources, imageRefs := collectDeploymentSourceK8sResources(controllers, entities)
	return controllers, k8sResources, imageRefs, nil
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
