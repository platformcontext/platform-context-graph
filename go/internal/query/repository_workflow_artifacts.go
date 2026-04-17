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

	contentFiles := make([]FileContent, 0, len(candidates))
	for _, file := range candidates {
		if !isGitHubActionsWorkflowFile(file) {
			continue
		}
		if strings.TrimSpace(file.Content) == "" {
			fileContent, err := reader.GetFileContent(ctx, repoID, file.RelativePath)
			if err != nil {
				return nil, fmt.Errorf("get workflow artifact file %q: %w", file.RelativePath, err)
			}
			if fileContent == nil {
				continue
			}
			file = *fileContent
		}
		contentFiles = append(contentFiles, file)
	}
	return buildRepositoryWorkflowArtifacts(contentFiles), nil
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
	reusableWorkflowRepositories, runCommands, gatingConditions, needsDependencies := workflowArtifactDetails(content)
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
	if len(gatingConditions) > 0 {
		row["gating_conditions"] = gatingConditions
		signals = append(signals, "gating_conditions")
	}
	if len(needsDependencies) > 0 {
		row["needs_dependencies"] = needsDependencies
		signals = append(signals, "job_dependencies")
	}
	if len(signals) > 0 {
		row["signals"] = uniqueWorkflowStringsPreserveOrder(signals)
	}
}

func workflowArtifactDetails(content string) ([]string, []string, []string, []string) {
	documents, err := decodeYAMLMaps(content)
	if err != nil {
		return nil, nil, nil, nil
	}

	reusableWorkflowRepositories := make([]string, 0)
	runCommands := make([]string, 0)
	gatingConditions := make([]string, 0)
	needsDependencies := make([]string, 0)
	for _, document := range documents {
		jobs, ok := document["jobs"].(map[string]any)
		if !ok {
			continue
		}
		for jobName, rawJob := range jobs {
			job, ok := rawJob.(map[string]any)
			if !ok {
				continue
			}
			if workflowRef := githubActionsReusableWorkflowRepoRef(StringVal(job, "uses")); workflowRef != "" {
				reusableWorkflowRepositories = append(reusableWorkflowRepositories, workflowRef)
			}
			if condition := strings.TrimSpace(StringVal(job, "if")); condition != "" {
				gatingConditions = append(gatingConditions, "job "+jobName+" if "+condition)
			}
			needsDependencies = append(needsDependencies, githubActionsNeedsDependencies(jobName, job["needs"])...)
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
					runCommand = ""
				}
				if condition := strings.TrimSpace(StringVal(step, "if")); condition != "" {
					gatingConditions = append(
						gatingConditions,
						"step "+jobName+"/"+workflowStepName(step)+" if "+condition,
					)
				}
				if runCommand == "" {
					continue
				}
				runCommands = append(runCommands, runCommand)
			}
		}
	}

	return sortedUniqueWorkflowStrings(reusableWorkflowRepositories),
		sortedUniqueWorkflowStrings(runCommands),
		sortedUniqueWorkflowStrings(gatingConditions),
		sortedUniqueWorkflowStrings(needsDependencies)
}

func githubActionsNeedsDependencies(jobName string, rawNeeds any) []string {
	needs := make([]string, 0, 2)
	switch value := rawNeeds.(type) {
	case string:
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			needs = append(needs, jobName+"<-"+trimmed)
		}
	case []any:
		for _, item := range value {
			trimmed := strings.TrimSpace(StringVal(map[string]any{"needs": item}, "needs"))
			if trimmed == "" {
				continue
			}
			needs = append(needs, jobName+"<-"+trimmed)
		}
	}
	return needs
}

func workflowStepName(step map[string]any) string {
	if name := strings.TrimSpace(StringVal(step, "name")); name != "" {
		return name
	}
	if uses := strings.TrimSpace(StringVal(step, "uses")); uses != "" {
		return uses
	}
	if run := strings.TrimSpace(StringVal(step, "run")); run != "" {
		return run
	}
	return "step"
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
