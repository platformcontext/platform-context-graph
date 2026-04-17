package query

import (
	"context"
	"fmt"
	"path/filepath"
	"sort"
	"strings"
)

func buildRepositoryWorkflowArtifacts(files []FileContent) map[string]any {
	artifacts := make([]map[string]any, 0)
	for _, file := range files {
		if !isGitHubActionsWorkflowFile(file) {
			continue
		}

		row := map[string]any{
			"relative_path": file.RelativePath,
			"artifact_type": "github_actions_workflow",
			"workflow_name": workflowArtifactName(file.RelativePath),
			"signals":       []string{"workflow_file"},
		}
		enrichWorkflowArtifactRow(row, file.Content)
		artifacts = append(artifacts, row)
	}
	if len(artifacts) == 0 {
		return nil
	}
	return map[string]any{"workflow_artifacts": artifacts}
}

func loadRepositoryWorkflowArtifacts(
	ctx context.Context,
	reader *ContentReader,
	repoID string,
	files []FileContent,
) (map[string]any, error) {
	if reader == nil || repoID == "" {
		return nil, nil
	}

	candidates := files
	if candidates == nil {
		var err error
		candidates, err = reader.ListRepoFiles(ctx, repoID, repositorySemanticEntityLimit)
		if err != nil {
			return nil, fmt.Errorf("list workflow artifact files: %w", err)
		}
	}
	return buildRepositoryWorkflowArtifacts(candidates), nil
}

func isGitHubActionsWorkflowFile(file FileContent) bool {
	if strings.EqualFold(file.ArtifactType, "github_actions_workflow") {
		return true
	}
	lower := strings.ToLower(filepath.ToSlash(strings.TrimSpace(file.RelativePath)))
	return strings.Contains(lower, ".github/workflows/") &&
		(strings.HasSuffix(lower, ".yml") || strings.HasSuffix(lower, ".yaml"))
}

func workflowArtifactName(relativePath string) string {
	base := filepath.Base(strings.TrimSpace(relativePath))
	if base == "" {
		return ""
	}
	ext := filepath.Ext(base)
	return strings.TrimSuffix(base, ext)
}

func enrichWorkflowArtifactRow(row map[string]any, content string) {
	reusableWorkflowRepositories, runCommands := workflowArtifactDetails(content)
	signals := stringSliceValue(row, "signals")

	if len(reusableWorkflowRepositories) > 0 {
		row["reusable_workflow_repositories"] = reusableWorkflowRepositories
		signals = append(signals, "reusable_workflow_refs")
	}
	if len(runCommands) > 0 {
		row["run_commands"] = runCommands
		row["command_count"] = len(runCommands)
		signals = append(signals, "run_commands")
	}
	if len(signals) > 0 {
		row["signals"] = uniqueWorkflowStringsPreserveOrder(signals)
	}
}

func workflowArtifactDetails(content string) ([]string, []string) {
	documents, err := decodeYAMLMaps(content)
	if err != nil {
		return nil, nil
	}

	reusableWorkflowRepositories := make([]string, 0)
	runCommands := make([]string, 0)
	for _, document := range documents {
		jobs, ok := document["jobs"].(map[string]any)
		if !ok {
			continue
		}
		for _, rawJob := range jobs {
			job, ok := rawJob.(map[string]any)
			if !ok {
				continue
			}
			if workflowRef := githubActionsReusableWorkflowRepoRef(StringVal(job, "uses")); workflowRef != "" {
				reusableWorkflowRepositories = append(reusableWorkflowRepositories, workflowRef)
			}
			steps, ok := job["steps"].([]any)
			if !ok {
				continue
			}
			for _, rawStep := range steps {
				step, ok := rawStep.(map[string]any)
				if !ok {
					continue
				}
				runCommand := strings.TrimSpace(StringVal(step, "run"))
				if runCommand == "" {
					continue
				}
				runCommands = append(runCommands, runCommand)
			}
		}
	}

	return sortedUniqueWorkflowStrings(reusableWorkflowRepositories), sortedUniqueWorkflowStrings(runCommands)
}

func sortedUniqueWorkflowStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}

	seen := make(map[string]struct{}, len(values))
	filtered := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		filtered = append(filtered, trimmed)
	}
	sort.Strings(filtered)
	return filtered
}

func uniqueWorkflowStringsPreserveOrder(values []string) []string {
	if len(values) == 0 {
		return nil
	}

	seen := make(map[string]struct{}, len(values))
	filtered := make([]string, 0, len(values))
	for _, value := range values {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			continue
		}
		if _, ok := seen[trimmed]; ok {
			continue
		}
		seen[trimmed] = struct{}{}
		filtered = append(filtered, trimmed)
	}
	return filtered
}
