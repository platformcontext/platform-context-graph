package query

import (
	"fmt"
	"sort"
	"strings"
)

// BuildRepositoryDeploymentOverview assembles the compact deployment summary for
// repository story responses from already-materialized read-model inputs.
func BuildRepositoryDeploymentOverview(
	workloads []string,
	platforms []string,
	infraFamilies []string,
	infrastructureOverview map[string]any,
) map[string]any {
	overview := map[string]any{
		"workload_count":          len(workloads),
		"platform_count":          len(platforms),
		"workloads":               workloads,
		"platforms":               platforms,
		"infrastructure_families": infraFamilies,
	}

	deploymentArtifacts := mapValue(infrastructureOverview, "deployment_artifacts")
	if len(deploymentArtifacts) > 0 {
		overview["deployment_artifacts"] = deploymentArtifacts
	}

	sharedConfigPaths := buildSharedConfigPaths(deploymentArtifacts)
	if len(sharedConfigPaths) > 0 {
		overview["shared_config_paths"] = sharedConfigPaths
	}

	topologyStory := buildTopologyStory(sharedConfigPaths)
	if len(topologyStory) > 0 {
		overview["topology_story"] = topologyStory
	}

	return overview
}

func buildSharedConfigPaths(deploymentArtifacts map[string]any) []map[string]any {
	rows := mapSliceValue(deploymentArtifacts, "config_paths")
	if len(rows) == 0 {
		return nil
	}

	grouped := map[string]map[string]struct{}{}
	for _, row := range rows {
		path := strings.TrimSpace(StringVal(row, "path"))
		sourceRepo := strings.TrimSpace(StringVal(row, "source_repo"))
		if path == "" || sourceRepo == "" {
			continue
		}
		if _, ok := grouped[path]; !ok {
			grouped[path] = map[string]struct{}{}
		}
		grouped[path][sourceRepo] = struct{}{}
	}

	paths := make([]string, 0, len(grouped))
	for path, repos := range grouped {
		if len(repos) > 1 {
			paths = append(paths, path)
		}
	}
	sort.Strings(paths)

	result := make([]map[string]any, 0, len(paths))
	for _, path := range paths {
		sourceRepos := sortedSetKeys(grouped[path])
		if len(sourceRepos) <= 1 {
			continue
		}
		result = append(result, map[string]any{
			"path":                path,
			"source_repositories": sourceRepos,
		})
	}
	return result
}

func buildTopologyStory(sharedConfigPaths []map[string]any) []string {
	if len(sharedConfigPaths) == 0 {
		return nil
	}

	families := make([]string, 0, len(sharedConfigPaths))
	for _, row := range sharedConfigPaths {
		path := strings.TrimSpace(StringVal(row, "path"))
		sourceRepos := stringSliceValue(row, "source_repositories")
		if path == "" || len(sourceRepos) == 0 {
			continue
		}
		families = append(families, fmt.Sprintf("%s across %s", path, strings.Join(sourceRepos, ", ")))
	}
	if len(families) == 0 {
		return nil
	}

	return []string{
		"Shared config families span " + joinSentenceFragments(families) + ".",
	}
}

func mapValue(value map[string]any, key string) map[string]any {
	if len(value) == 0 {
		return nil
	}
	raw, ok := value[key]
	if !ok {
		return nil
	}
	typed, ok := raw.(map[string]any)
	if !ok || len(typed) == 0 {
		return nil
	}
	return typed
}

func mapSliceValue(value map[string]any, key string) []map[string]any {
	if len(value) == 0 {
		return nil
	}
	raw, ok := value[key]
	if !ok {
		return nil
	}
	items, ok := raw.([]map[string]any)
	if ok {
		return items
	}
	typed, ok := raw.([]any)
	if !ok {
		return nil
	}
	result := make([]map[string]any, 0, len(typed))
	for _, item := range typed {
		row, ok := item.(map[string]any)
		if ok {
			result = append(result, row)
		}
	}
	return result
}

func stringSliceValue(value map[string]any, key string) []string {
	if len(value) == 0 {
		return nil
	}
	raw, ok := value[key]
	if !ok {
		return nil
	}
	switch typed := raw.(type) {
	case []string:
		return nonEmptyStrings(typed)
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			text, ok := item.(string)
			if ok && strings.TrimSpace(text) != "" {
				result = append(result, strings.TrimSpace(text))
			}
		}
		return result
	default:
		return nil
	}
}

func sortedSetKeys(values map[string]struct{}) []string {
	keys := make([]string, 0, len(values))
	for key := range values {
		if strings.TrimSpace(key) == "" {
			continue
		}
		keys = append(keys, key)
	}
	sort.Strings(keys)
	return keys
}
