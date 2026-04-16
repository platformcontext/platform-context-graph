package query

import (
	"path/filepath"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func buildRepositoryControllerArtifacts(repoName string, files []FileContent) map[string]any {
	artifacts := make([]map[string]any, 0)
	for _, file := range files {
		metadata := parser.ExtractGroovyPipelineMetadata(file.Content)
		if !isJenkinsGroovyArtifact(file, metadata) {
			continue
		}
		row := map[string]any{
			"path":            cleanRepositoryRelativePath(file.RelativePath),
			"source_repo":     repoName,
			"relative_path":   file.RelativePath,
			"controller_kind": "jenkins_pipeline",
		}

		if sharedLibraries := stringSliceValue(metadata, "shared_libraries"); len(sharedLibraries) > 0 {
			row["shared_libraries"] = sharedLibraries
		}
		if pipelineCalls := stringSliceValue(metadata, "pipeline_calls"); len(pipelineCalls) > 0 {
			row["pipeline_calls"] = pipelineCalls
		}
		if entryPoints := stringSliceValue(metadata, "entry_points"); len(entryPoints) > 0 {
			row["entry_points"] = entryPoints
		}
		if shellCommands := stringSliceValue(metadata, "shell_commands"); len(shellCommands) > 0 {
			row["shell_commands"] = shellCommands
		}
		if hints := mapSliceValue(metadata, "ansible_playbook_hints"); len(hints) > 0 {
			row["ansible_playbook_hints"] = hints
		}
		if useConfigd, ok := metadata["use_configd"].(bool); ok {
			row["use_configd"] = useConfigd
		}
		if hasPreDeploy, ok := metadata["has_pre_deploy"].(bool); ok {
			row["has_pre_deploy"] = hasPreDeploy
		}

		artifacts = append(artifacts, row)
	}

	if len(artifacts) == 0 {
		return nil
	}

	sort.SliceStable(artifacts, func(i, j int) bool {
		leftPath := StringVal(artifacts[i], "path")
		rightPath := StringVal(artifacts[j], "path")
		if leftPath != rightPath {
			return leftPath < rightPath
		}
		return StringVal(artifacts[i], "relative_path") < StringVal(artifacts[j], "relative_path")
	})

	return map[string]any{"controller_artifacts": artifacts}
}

func isJenkinsGroovyArtifact(file FileContent, metadata map[string]any) bool {
	base := strings.TrimSpace(file.RelativePath)
	if base == "" {
		return false
	}
	name := strings.ToLower(filepath.Base(base))
	if name == "jenkinsfile" {
		return true
	}
	if strings.HasPrefix(name, "jenkinsfile.") {
		return true
	}
	if !strings.HasSuffix(name, ".groovy") {
		return false
	}
	return groovyPipelineMetadataPresent(metadata)
}

func groovyPipelineMetadataPresent(metadata map[string]any) bool {
	if len(metadata) == 0 {
		return false
	}
	if values := stringSliceValue(metadata, "shared_libraries"); len(values) > 0 {
		return true
	}
	if values := stringSliceValue(metadata, "pipeline_calls"); len(values) > 0 {
		return true
	}
	if values := stringSliceValue(metadata, "shell_commands"); len(values) > 0 {
		return true
	}
	if values := stringSliceValue(metadata, "entry_points"); len(values) > 0 {
		return true
	}
	if useConfigd, ok := metadata["use_configd"].(bool); ok && useConfigd {
		return true
	}
	if hasPreDeploy, ok := metadata["has_pre_deploy"].(bool); ok && hasPreDeploy {
		return true
	}
	return false
}
