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
		entry := map[string]any{
			"path":            path,
			"kind":            "controller_artifact",
			"controller_kind": controllerKind,
		}
		copyStringSliceField(entry, row, "shared_libraries")
		copyStringSliceField(entry, row, "pipeline_calls")
		copyStringSliceField(entry, row, "entry_points")
		copyStringSliceField(entry, row, "ansible_inventories")
		copyStringSliceField(entry, row, "ansible_var_files")
		copyStringSliceField(entry, row, "ansible_task_entrypoints")
		copyStringSliceField(entry, row, "ansible_role_paths")
		if hints := mapSliceValue(row, "ansible_playbook_hints"); len(hints) > 0 {
			entry["ansible_playbook_hints"] = hints
		}
		paths = append(paths, entry)
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
		if artifactName := strings.TrimSpace(StringVal(row, "artifact_name")); artifactName != "" {
			entry["artifact_name"] = artifactName
		}
		if baseImage := strings.TrimSpace(StringVal(row, "base_image")); baseImage != "" {
			entry["base_image"] = baseImage
		}
		if buildContext := strings.TrimSpace(StringVal(row, "build_context")); buildContext != "" {
			entry["build_context"] = buildContext
		}
		if serviceName := strings.TrimSpace(StringVal(row, "service_name")); serviceName != "" {
			entry["service_name"] = serviceName
		}
		if cmd := strings.TrimSpace(StringVal(row, "cmd")); cmd != "" {
			entry["cmd"] = cmd
		}
		if signals := stringSliceValue(row, "signals"); len(signals) > 0 {
			entry["signals"] = signals
		}
		paths = append(paths, entry)
	}

	for _, row := range mapSliceValue(deploymentArtifacts, "workflow_artifacts") {
		path := strings.TrimSpace(StringVal(row, "relative_path"))
		artifactType := strings.TrimSpace(StringVal(row, "artifact_type"))
		if path == "" || artifactType == "" {
			continue
		}
		entry := map[string]any{
			"path":          path,
			"kind":          "workflow_artifact",
			"artifact_type": artifactType,
		}
		if workflowName := strings.TrimSpace(StringVal(row, "workflow_name")); workflowName != "" {
			entry["workflow_name"] = workflowName
		}
		if signals := stringSliceValue(row, "signals"); len(signals) > 0 {
			entry["signals"] = signals
		}
		paths = append(paths, entry)
	}

	for _, row := range mapSliceValue(deploymentArtifacts, "config_paths") {
		path := strings.TrimSpace(StringVal(row, "path"))
		sourceRepo := strings.TrimSpace(StringVal(row, "source_repo"))
		relativePath := strings.TrimSpace(StringVal(row, "relative_path"))
		evidenceKind := strings.TrimSpace(StringVal(row, "evidence_kind"))
		if path == "" || sourceRepo == "" || relativePath == "" || evidenceKind == "" {
			continue
		}
		paths = append(paths, map[string]any{
			"path":          path,
			"kind":          "config_artifact",
			"source_repo":   sourceRepo,
			"relative_path": relativePath,
			"evidence_kind": evidenceKind,
		})
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
		copyStringSliceField(entry, row, "ansible_inventories")
		copyStringSliceField(entry, row, "ansible_var_files")
		copyStringSliceField(entry, row, "ansible_task_entrypoints")
		copyStringSliceField(entry, row, "ansible_role_paths")
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

	type sharedConfigAggregate struct {
		sourceRepos   map[string]struct{}
		evidenceKinds map[string]struct{}
		relativePaths map[string]struct{}
	}

	grouped := map[string]*sharedConfigAggregate{}
	for _, row := range rows {
		path := strings.TrimSpace(StringVal(row, "path"))
		sourceRepo := strings.TrimSpace(StringVal(row, "source_repo"))
		if path == "" || sourceRepo == "" {
			continue
		}
		aggregate, ok := grouped[path]
		if !ok {
			aggregate = &sharedConfigAggregate{
				sourceRepos:   map[string]struct{}{},
				evidenceKinds: map[string]struct{}{},
				relativePaths: map[string]struct{}{},
			}
			grouped[path] = aggregate
		}
		aggregate.sourceRepos[sourceRepo] = struct{}{}
		if evidenceKind := strings.TrimSpace(StringVal(row, "evidence_kind")); evidenceKind != "" {
			aggregate.evidenceKinds[evidenceKind] = struct{}{}
		}
		if relativePath := strings.TrimSpace(StringVal(row, "relative_path")); relativePath != "" {
			aggregate.relativePaths[relativePath] = struct{}{}
		}
	}

	paths := make([]string, 0, len(grouped))
	for path, aggregate := range grouped {
		if len(aggregate.sourceRepos) > 1 {
			paths = append(paths, path)
		}
	}
	sort.Strings(paths)

	result := make([]map[string]any, 0, len(paths))
	for _, path := range paths {
		aggregate := grouped[path]
		sourceRepos := sortedSetKeys(aggregate.sourceRepos)
		if len(sourceRepos) <= 1 {
			continue
		}
		entry := map[string]any{
			"path":                path,
			"source_repositories": sourceRepos,
		}
		if evidenceKinds := sortedSetKeys(aggregate.evidenceKinds); len(evidenceKinds) > 0 {
			entry["evidence_kinds"] = evidenceKinds
		}
		if relativePaths := sortedSetKeys(aggregate.relativePaths); len(relativePaths) > 0 {
			entry["relative_paths"] = relativePaths
		}
		result = append(result, entry)
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
			details := make([]string, 0, 3)
			if entryPoints := stringSliceValue(row, "entry_points"); len(entryPoints) > 0 {
				details = append(details, "entry points "+strings.Join(entryPoints, ", "))
			}
			if sharedLibraries := stringSliceValue(row, "shared_libraries"); len(sharedLibraries) > 0 {
				details = append(details, "shared libraries "+strings.Join(sharedLibraries, ", "))
			}
			if pipelineCalls := stringSliceValue(row, "pipeline_calls"); len(pipelineCalls) > 0 {
				details = append(details, "pipeline calls "+strings.Join(pipelineCalls, ", "))
			}
			if hints := mapSliceValue(row, "ansible_playbook_hints"); len(hints) > 0 {
				playbooks := make([]string, 0, len(hints))
				for _, hint := range hints {
					if playbook := strings.TrimSpace(StringVal(hint, "playbook")); playbook != "" {
						playbooks = append(playbooks, playbook)
					}
				}
				if len(playbooks) > 0 {
					details = append(details, "ansible playbooks "+strings.Join(playbooks, ", "))
				}
			}
			if inventories := stringSliceValue(row, "ansible_inventories"); len(inventories) > 0 {
				details = append(details, "ansible inventories "+strings.Join(inventories, ", "))
			}
			if varFiles := stringSliceValue(row, "ansible_var_files"); len(varFiles) > 0 {
				details = append(details, "ansible vars "+strings.Join(varFiles, ", "))
			}
			if taskEntrypoints := stringSliceValue(row, "ansible_task_entrypoints"); len(taskEntrypoints) > 0 {
				details = append(details, "ansible task entrypoints "+strings.Join(taskEntrypoints, ", "))
			}
			line := fmt.Sprintf("Controller delivery paths include %s via %s", path, controllerKind)
			if len(details) > 0 {
				line += " (" + strings.Join(details, "; ") + ")"
			}
			story = append(story, line+".")
		case "runtime_artifact":
			path := strings.TrimSpace(StringVal(row, "path"))
			artifactType := strings.TrimSpace(StringVal(row, "artifact_type"))
			artifactName := strings.TrimSpace(StringVal(row, "artifact_name"))
			serviceName := strings.TrimSpace(StringVal(row, "service_name"))
			baseImage := strings.TrimSpace(StringVal(row, "base_image"))
			cmd := strings.TrimSpace(StringVal(row, "cmd"))
			buildContext := strings.TrimSpace(StringVal(row, "build_context"))
			signals := stringSliceValue(row, "signals")
			if path == "" || artifactType == "" {
				continue
			}
			line := buildRuntimeArtifactStoryLine(artifactType, artifactName, serviceName, path, baseImage, cmd)
			if line == "" {
				continue
			}
			if buildContext != "" && serviceName != "" {
				line += fmt.Sprintf(" built from %s", buildContext)
			}
			if len(signals) > 0 {
				line += fmt.Sprintf(" (%s)", strings.Join(signals, ", "))
			}
			story = append(story, line+".")
		case "config_artifact":
			path := strings.TrimSpace(StringVal(row, "path"))
			sourceRepo := strings.TrimSpace(StringVal(row, "source_repo"))
			relativePath := strings.TrimSpace(StringVal(row, "relative_path"))
			evidenceKind := strings.TrimSpace(StringVal(row, "evidence_kind"))
			if path == "" || sourceRepo == "" || relativePath == "" || evidenceKind == "" {
				continue
			}
			story = append(story, fmt.Sprintf(
				"Config provenance includes %s from %s via %s in %s.",
				path,
				sourceRepo,
				evidenceKind,
				relativePath,
			))
		case "workflow_artifact":
			path := strings.TrimSpace(StringVal(row, "path"))
			artifactType := strings.TrimSpace(StringVal(row, "artifact_type"))
			workflowName := strings.TrimSpace(StringVal(row, "workflow_name"))
			if path == "" || artifactType == "" {
				continue
			}
			line := fmt.Sprintf("Workflow delivery paths include %s", path)
			if workflowName != "" {
				line += fmt.Sprintf(" as %s %s", artifactType, workflowName)
			}
			if signals := stringSliceValue(row, "signals"); len(signals) > 0 {
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

func buildRuntimeArtifactStoryLine(artifactType, artifactName, serviceName, path, baseImage, cmd string) string {
	switch {
	case serviceName != "":
		line := fmt.Sprintf("Runtime artifacts include %s service %s in %s", artifactType, serviceName, path)
		if cmd != "" {
			line += fmt.Sprintf(" with cmd %s", cmd)
		}
		return line
	case artifactName != "":
		line := fmt.Sprintf("Runtime artifacts include %s stage %s in %s", artifactType, artifactName, path)
		if baseImage != "" {
			line += fmt.Sprintf(" based on %s", baseImage)
		}
		if cmd != "" {
			line += fmt.Sprintf(" with cmd %s", cmd)
		}
		return line
	default:
		return ""
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
