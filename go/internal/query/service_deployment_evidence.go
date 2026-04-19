package query

import (
	"context"
	"sort"
	"strings"
)

func loadServiceDeploymentEvidence(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	workloadContext map[string]any,
) (map[string]any, error) {
	if content == nil || len(workloadContext) == 0 {
		return nil, nil
	}

	repoID := safeStr(workloadContext, "repo_id")
	repoName := safeStr(workloadContext, "repo_name")
	if repoID == "" || repoName == "" {
		return nil, nil
	}

	files, err := content.ListRepoFiles(ctx, repoID, repositorySemanticEntityLimit)
	if err != nil {
		return nil, err
	}
	if files == nil {
		files = []FileContent{}
	}

	overview := buildRepositoryInfrastructureOverview(
		mapSliceValue(workloadContext, "infrastructure"),
		files,
	)
	overview, err = loadDeploymentArtifactOverview(
		ctx,
		graph,
		content,
		repoID,
		repoName,
		files,
		overview,
	)
	if err != nil {
		return nil, err
	}
	if relationshipOverview := buildRepositoryRelationshipOverview(mapSliceValue(workloadContext, "dependencies")); relationshipOverview != nil {
		if overview == nil {
			overview = map[string]any{}
		}
		overview["relationship_overview"] = relationshipOverview
	}
	return buildServiceDeploymentEvidenceFromOverview(overview), nil
}

func buildServiceDeploymentEvidenceFromOverview(overview map[string]any) map[string]any {
	if len(overview) == 0 {
		return nil
	}

	evidence := map[string]any{}
	repositoryOverview := BuildRepositoryDeploymentOverview(
		nil,
		nil,
		collectServiceDeploymentToolFamilies(overview),
		overview,
	)
	for _, key := range []string{
		"deployment_artifacts",
		"shared_config_paths",
		"delivery_paths",
		"delivery_family_paths",
		"delivery_family_story",
		"delivery_workflows",
		"topology_story",
	} {
		if value, ok := repositoryOverview[key]; ok && value != nil {
			evidence[key] = value
		}
	}
	if toolFamilies := collectServiceDeploymentToolFamilies(overview); len(toolFamilies) > 0 {
		evidence["tool_families"] = toolFamilies
	}
	if relationshipOverview := mapValue(overview, "relationship_overview"); len(relationshipOverview) > 0 {
		evidence["relationship_overview"] = relationshipOverview
	}
	return evidence
}

func collectServiceDeploymentToolFamilies(overview map[string]any) []string {
	families := map[string]struct{}{}
	for _, family := range stringSliceMapValue(overview, "families") {
		if trimmed := strings.TrimSpace(family); trimmed != "" {
			families[trimmed] = struct{}{}
		}
	}
	for _, row := range mapSliceValue(mapValue(overview, "deployment_artifacts"), "controller_artifacts") {
		switch strings.TrimSpace(StringVal(row, "controller_kind")) {
		case "jenkins_pipeline":
			families["jenkins"] = struct{}{}
		}
	}
	for _, row := range mapSliceValue(overview, "delivery_family_paths") {
		if toolFamily := strings.TrimSpace(StringVal(row, "tool_family")); toolFamily != "" {
			families[toolFamily] = struct{}{}
		}
	}

	sorted := make([]string, 0, len(families))
	for family := range families {
		sorted = append(sorted, family)
	}
	sort.Strings(sorted)
	return sorted
}

func mergeTraceRepositoryDeliveryPaths(
	paths []map[string]any,
	deploymentEvidence map[string]any,
) []map[string]any {
	if len(deploymentEvidence) == 0 {
		return paths
	}

	seen := make(map[string]struct{}, len(paths))
	merged := make([]map[string]any, 0, len(paths)+len(mapSliceValue(deploymentEvidence, "delivery_paths")))
	for _, row := range paths {
		key := deploymentTraceDeliveryPathKey(row)
		seen[key] = struct{}{}
		merged = append(merged, row)
	}
	for _, row := range mapSliceValue(deploymentEvidence, "delivery_paths") {
		entry := cloneAnyMap(row)
		if StringVal(entry, "type") == "" {
			entry["type"] = "repository_delivery_artifact"
		}
		key := deploymentTraceDeliveryPathKey(entry)
		if _, ok := seen[key]; ok {
			continue
		}
		seen[key] = struct{}{}
		merged = append(merged, entry)
	}
	return merged
}

func cloneAnyMap(src map[string]any) map[string]any {
	if len(src) == 0 {
		return map[string]any{}
	}
	dst := make(map[string]any, len(src))
	for key, value := range src {
		dst[key] = value
	}
	return dst
}

func deploymentTraceDeliveryPathKey(row map[string]any) string {
	return strings.Join([]string{
		StringVal(row, "type"),
		StringVal(row, "kind"),
		StringVal(row, "path"),
		StringVal(row, "relative_path"),
		StringVal(row, "target"),
	}, "|")
}
