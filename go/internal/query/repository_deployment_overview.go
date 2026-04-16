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

	deliveryPaths := buildOverviewDeliveryPaths(deploymentArtifacts)
	if len(deliveryPaths) > 0 {
		overview["delivery_paths"] = deliveryPaths
	}

	deliveryWorkflows := buildOverviewDeliveryWorkflows(deploymentArtifacts)
	if len(deliveryWorkflows) > 0 {
		overview["delivery_workflows"] = deliveryWorkflows
	}

	topologyStory := buildOverviewTopologyStory(deliveryPaths, sharedConfigPaths)
	if len(topologyStory) > 0 {
		overview["topology_story"] = topologyStory
	}

	return overview
}

func buildOverviewDeliveryPaths(deploymentArtifacts map[string]any) []map[string]any {
	paths := make([]map[string]any, 0)

	for _, row := range mapSliceValue(deploymentArtifacts, "controller_artifacts") {
		path := strings.TrimSpace(StringVal(row, "path"))
		controllerKind := strings.TrimSpace(StringVal(row, "controller_kind"))
		if path == "" || controllerKind == "" {
			continue
		}
		paths = append(paths, map[string]any{
			"path":            path,
			"kind":            "controller_artifact",
			"controller_kind": controllerKind,
		})
	}

	for _, row := range mapSliceValue(deploymentArtifacts, "deployment_artifacts") {
		path := strings.TrimSpace(StringVal(row, "relative_path"))
		artifactType := strings.TrimSpace(StringVal(row, "artifact_type"))
		if path == "" || artifactType == "" {
			continue
		}
		entry := map[string]any{
			"path":          path,
			"kind":          "runtime_artifact",
			"artifact_type": artifactType,
		}
		if serviceName := strings.TrimSpace(StringVal(row, "service_name")); serviceName != "" {
			entry["service_name"] = serviceName
		}
		if signals := stringSliceValue(row, "signals"); len(signals) > 0 {
			entry["signals"] = signals
		}
		paths = append(paths, entry)
	}

	sort.Slice(paths, func(i, j int) bool {
		leftPath := StringVal(paths[i], "path")
		rightPath := StringVal(paths[j], "path")
		if leftPath != rightPath {
			return leftPath < rightPath
		}
		return StringVal(paths[i], "kind") < StringVal(paths[j], "kind")
	})

	return paths
}

func buildOverviewDeliveryWorkflows(deploymentArtifacts map[string]any) []map[string]any {
	rows := mapSliceValue(deploymentArtifacts, "controller_artifacts")
	if len(rows) == 0 {
		return nil
	}

	workflows := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		path := strings.TrimSpace(StringVal(row, "path"))
		controllerKind := strings.TrimSpace(StringVal(row, "controller_kind"))
		if path == "" || controllerKind == "" {
			continue
		}
		entry := map[string]any{
			"path":            path,
			"controller_kind": controllerKind,
		}
		copyStringSliceField(entry, row, "shared_libraries")
		copyStringSliceField(entry, row, "pipeline_calls")
		copyStringSliceField(entry, row, "entry_points")
		copyStringSliceField(entry, row, "shell_commands")
		if hints := mapSliceValue(row, "ansible_playbook_hints"); len(hints) > 0 {
			entry["ansible_playbook_hints"] = hints
		}
		workflows = append(workflows, entry)
	}

	sort.Slice(workflows, func(i, j int) bool {
		return StringVal(workflows[i], "path") < StringVal(workflows[j], "path")
	})

	return workflows
}

func copyStringSliceField(dst map[string]any, src map[string]any, key string) {
	if values := stringSliceValue(src, key); len(values) > 0 {
		dst[key] = values
	}
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

func buildOverviewTopologyStory(deliveryPaths []map[string]any, sharedConfigPaths []map[string]any) []string {
	story := make([]string, 0, len(deliveryPaths)+1)
	for _, row := range deliveryPaths {
		switch StringVal(row, "kind") {
		case "controller_artifact":
			path := strings.TrimSpace(StringVal(row, "path"))
			controllerKind := strings.TrimSpace(StringVal(row, "controller_kind"))
			if path == "" || controllerKind == "" {
				continue
			}
			story = append(story, fmt.Sprintf("Controller delivery paths include %s via %s.", path, controllerKind))
		case "runtime_artifact":
			path := strings.TrimSpace(StringVal(row, "path"))
			artifactType := strings.TrimSpace(StringVal(row, "artifact_type"))
			serviceName := strings.TrimSpace(StringVal(row, "service_name"))
			signals := stringSliceValue(row, "signals")
			if path == "" || artifactType == "" || serviceName == "" {
				continue
			}
			line := fmt.Sprintf("Runtime artifacts include %s service %s in %s", artifactType, serviceName, path)
			if len(signals) > 0 {
				line += fmt.Sprintf(" (%s)", strings.Join(signals, ", "))
			}
			story = append(story, line+".")
		}
	}

	if len(sharedConfigPaths) > 0 {
		families := make([]string, 0, len(sharedConfigPaths))
		for _, row := range sharedConfigPaths {
			path := strings.TrimSpace(StringVal(row, "path"))
			sourceRepos := stringSliceValue(row, "source_repositories")
			if path == "" || len(sourceRepos) == 0 {
				continue
			}
			families = append(families, fmt.Sprintf("%s across %s", path, strings.Join(sourceRepos, ", ")))
		}
		if len(families) > 0 {
			story = append(story, "Shared config families span "+joinSentenceFragments(families)+".")
		}
	}

	return story
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
