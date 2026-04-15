package query

import (
	"fmt"
	"strings"
)

func buildRepositoryStoryResponse(
	repo RepoRef,
	fileCount int,
	languages []string,
	workloads []string,
	platforms []string,
	dependencyCount int,
) map[string]any {
	filteredLanguages := nonEmptyStrings(languages)
	filteredPlatforms := nonEmptyStrings(platforms)
	filteredWorkloads := nonEmptyStrings(workloads)
	limitations := []string{"coverage_not_computed"}
	if len(filteredPlatforms) == 0 {
		limitations = append(limitations, "deployment_surface_unknown")
	}
	if len(filteredWorkloads) == 0 {
		limitations = append(limitations, "workload_surface_unknown")
	}

	return map[string]any{
		"repository": repo,
		"subject": map[string]any{
			"type": "repository",
			"id":   repo.ID,
			"name": repo.Name,
		},
		"story": buildRepositoryStory(
			repo,
			fileCount,
			filteredLanguages,
			filteredWorkloads,
			filteredPlatforms,
		),
		"story_sections": []map[string]any{
			{
				"title":   "codebase",
				"summary": fmt.Sprintf("%d indexed file(s) across %d language family(s)", fileCount, len(filteredLanguages)),
			},
			{
				"title":   "deployment",
				"summary": fmt.Sprintf("%d workload(s) and %d platform signal(s)", len(filteredWorkloads), len(filteredPlatforms)),
			},
			{
				"title":   "support",
				"summary": fmt.Sprintf("%d dependency link(s) and remote=%t", dependencyCount, repo.HasRemote),
			},
		},
		"deployment_overview": map[string]any{
			"workload_count": len(filteredWorkloads),
			"platform_count": len(filteredPlatforms),
			"workloads":      filteredWorkloads,
			"platforms":      filteredPlatforms,
		},
		"gitops_overview": map[string]any{
			"enabled":          containsGitOpsPlatform(filteredPlatforms),
			"tool_families":    filteredPlatforms,
			"observed_targets": filteredWorkloads,
		},
		"documentation_overview": map[string]any{
			"repo_slug":           repo.RepoSlug,
			"remote_url":          repo.RemoteURL,
			"has_remote":          repo.HasRemote,
			"local_path_present":  repo.LocalPath != "",
			"portable_identifier": repo.ID,
		},
		"support_overview": map[string]any{
			"dependency_count": dependencyCount,
			"language_count":   len(filteredLanguages),
			"languages":        filteredLanguages,
		},
		"coverage_summary": map[string]any{
			"status": "unknown",
			"reason": "repository_story_does_not_yet_compute_completeness",
		},
		"limitations": limitations,
		"drilldowns": map[string]any{
			"context_path":  "/api/v0/repositories/" + repo.ID + "/context",
			"stats_path":    "/api/v0/repositories/" + repo.ID + "/stats",
			"coverage_path": "/api/v0/repositories/" + repo.ID + "/coverage",
		},
	}
}

func buildRepositoryStory(
	repo RepoRef,
	fileCount int,
	languages []string,
	workloads []string,
	platforms []string,
) string {
	parts := []string{
		fmt.Sprintf("Repository %s contains %d indexed files.", repo.Name, fileCount),
	}

	if len(languages) > 0 {
		parts = append(parts, fmt.Sprintf("Languages: %s.", strings.Join(languages, ", ")))
	}
	if len(workloads) > 0 {
		parts = append(parts, fmt.Sprintf("Defines %d workload(s): %s.", len(workloads), strings.Join(workloads, ", ")))
	}
	if len(platforms) > 0 {
		parts = append(parts, fmt.Sprintf("Runs on platform signal(s): %s.", strings.Join(platforms, ", ")))
	}
	if repo.HasRemote && repo.RemoteURL != "" {
		parts = append(parts, fmt.Sprintf("Remote URL: %s.", repo.RemoteURL))
	}

	return strings.Join(parts, " ")
}

func nonEmptyStrings(values []string) []string {
	filtered := make([]string, 0, len(values))
	for _, value := range values {
		if value == "" {
			continue
		}
		filtered = append(filtered, value)
	}
	return filtered
}

func containsGitOpsPlatform(platforms []string) bool {
	for _, platform := range platforms {
		switch platform {
		case "argocd_application", "argocd_applicationset", "flux_kustomization", "flux_helmrelease":
			return true
		}
	}
	return false
}
