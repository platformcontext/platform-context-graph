package relationships

import "strings"

func discoverGitHubActionsEvidence(
	sourceRepoID, filePath, content string,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact
	for _, document := range parseYAMLDocuments(content) {
		for _, workflowPath := range githubActionsLocalReusableWorkflowPaths(document) {
			key := evidenceKey{
				EvidenceKind: EvidenceKindGitHubActionsLocalReusableWorkflow,
				SourceRepoID: sourceRepoID,
				TargetRepoID: sourceRepoID,
				Path:         filePath,
				MatchedValue: workflowPath,
			}
			if _, ok := seen[key]; ok {
				continue
			}
			seen[key] = struct{}{}
			evidence = append(evidence, EvidenceFact{
				EvidenceKind:     EvidenceKindGitHubActionsLocalReusableWorkflow,
				RelationshipType: RelDeploysFrom,
				SourceRepoID:     sourceRepoID,
				TargetRepoID:     sourceRepoID,
				Confidence:       0.86,
				Rationale:        "GitHub Actions reuses deployment logic from a workflow file in the same repository",
				Details: map[string]any{
					"path":                filePath,
					"matched_alias":       sourceRepoID,
					"matched_value":       workflowPath,
					"extractor":           "github_actions",
					"local_workflow_path": workflowPath,
				},
			})
		}
		for _, candidate := range githubActionsReusableWorkflowRefs(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindGitHubActionsReusableWorkflow, RelDeploysFrom, 0.93,
				"GitHub Actions reusable workflow references deployment logic in the target repository",
				"github_actions", catalog, seen, map[string]any{
					"workflow_ref": candidate,
				},
			)...)
		}
		for _, candidate := range githubActionsCheckoutRepositoryRefs(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindGitHubActionsCheckoutRepository, RelDiscoversConfigIn, 0.91,
				"GitHub Actions explicitly checks out config or automation from the target repository",
				"github_actions", catalog, seen, map[string]any{
					"checkout_repository": candidate,
				},
			)...)
		}
		for _, candidate := range githubActionsWorkflowInputRepositoryRefs(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindGitHubActionsWorkflowInputRepository, RelDiscoversConfigIn, 0.90,
				"GitHub Actions passes an explicit automation or config repository through workflow inputs",
				"github_actions", catalog, seen, map[string]any{
					"workflow_input_repository": candidate,
				},
			)...)
		}
		for _, candidate := range githubActionsActionRepositoryRefs(document) {
			evidence = append(evidence, matchCatalog(
				sourceRepoID, candidate, filePath,
				EvidenceKindGitHubActionsActionRepository, RelDependsOn, 0.88,
				"GitHub Actions step uses the target repository as an action dependency",
				"github_actions", catalog, seen, map[string]any{
					"action_repository": candidate,
				},
			)...)
		}
	}
	return evidence
}

func githubActionsReusableWorkflowRefs(document map[string]any) []string {
	jobsValue, ok := document["jobs"]
	if !ok {
		return nil
	}

	jobs, ok := jobsValue.(map[string]any)
	if !ok {
		return nil
	}

	refs := make([]string, 0, len(jobs))
	for _, rawJob := range jobs {
		job, ok := rawJob.(map[string]any)
		if !ok {
			continue
		}
		if workflowRef := reusableWorkflowRepoRef(stringValue(job["uses"])); workflowRef != "" {
			refs = append(refs, workflowRef)
		}
	}

	return uniqueStrings(refs)
}

func githubActionsLocalReusableWorkflowPaths(document map[string]any) []string {
	jobsValue, ok := document["jobs"]
	if !ok {
		return nil
	}

	jobs, ok := jobsValue.(map[string]any)
	if !ok {
		return nil
	}

	paths := make([]string, 0, len(jobs))
	for _, rawJob := range jobs {
		job, ok := rawJob.(map[string]any)
		if !ok {
			continue
		}
		if workflowPath := githubActionsLocalReusableWorkflowPath(stringValue(job["uses"])); workflowPath != "" {
			paths = append(paths, workflowPath)
		}
	}

	return uniqueStrings(paths)
}

func githubActionsCheckoutRepositoryRefs(document map[string]any) []string {
	jobsValue, ok := document["jobs"]
	if !ok {
		return nil
	}

	jobs, ok := jobsValue.(map[string]any)
	if !ok {
		return nil
	}

	refs := make([]string, 0)
	for _, rawJob := range jobs {
		job, ok := rawJob.(map[string]any)
		if !ok {
			continue
		}
		for _, rawStep := range sliceValue(job["steps"]) {
			step, ok := rawStep.(map[string]any)
			if !ok {
				continue
			}
			if !strings.HasPrefix(strings.TrimSpace(stringValue(step["uses"])), "actions/checkout@") {
				continue
			}
			withMap, _ := nestedMap(step, "with")
			if withMap == nil {
				continue
			}
			if repoRef := strings.TrimSpace(stringValue(withMap["repository"])); repoRef != "" {
				refs = append(refs, repoRef)
			}
		}
	}

	return uniqueStrings(refs)
}

func githubActionsWorkflowInputRepositoryRefs(document map[string]any) []string {
	jobsValue, ok := document["jobs"]
	if !ok {
		return nil
	}

	jobs, ok := jobsValue.(map[string]any)
	if !ok {
		return nil
	}

	refs := make([]string, 0, len(jobs))
	for _, rawJob := range jobs {
		job, ok := rawJob.(map[string]any)
		if !ok {
			continue
		}
		withMap, _ := nestedMap(job, "with")
		if withMap == nil {
			continue
		}
		for _, key := range []string{"workflow_input_repository", "automation-repo", "automation_repo"} {
			if repoRef := strings.TrimSpace(stringValue(withMap[key])); repoRef != "" {
				refs = append(refs, repoRef)
			}
		}
	}

	return uniqueStrings(refs)
}

func githubActionsActionRepositoryRefs(document map[string]any) []string {
	jobsValue, ok := document["jobs"]
	if !ok {
		return nil
	}

	jobs, ok := jobsValue.(map[string]any)
	if !ok {
		return nil
	}

	refs := make([]string, 0)
	for _, rawJob := range jobs {
		job, ok := rawJob.(map[string]any)
		if !ok {
			continue
		}
		for _, rawStep := range sliceValue(job["steps"]) {
			step, ok := rawStep.(map[string]any)
			if !ok {
				continue
			}
			if repoRef := githubActionsActionRepoRef(stringValue(step["uses"])); repoRef != "" {
				refs = append(refs, repoRef)
			}
		}
	}

	return uniqueStrings(refs)
}

func reusableWorkflowRepoRef(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	at := strings.Index(trimmed, "@")
	if at >= 0 {
		trimmed = trimmed[:at]
	}
	parts := strings.Split(trimmed, "/")
	if len(parts) < 3 {
		return ""
	}
	if parts[0] == "." {
		return ""
	}
	if parts[2] != ".github" {
		return ""
	}
	return strings.Join(parts[:2], "/")
}

func githubActionsActionRepoRef(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" || strings.HasPrefix(trimmed, "docker://") {
		return ""
	}
	if strings.HasPrefix(trimmed, "actions/checkout@") {
		return ""
	}
	at := strings.Index(trimmed, "@")
	if at >= 0 {
		trimmed = trimmed[:at]
	}
	if strings.HasPrefix(trimmed, "./") || strings.HasPrefix(trimmed, ".github/") {
		return ""
	}
	if repoRef := reusableWorkflowRepoRef(trimmed); repoRef != "" {
		return ""
	}
	parts := strings.Split(trimmed, "/")
	if len(parts) < 2 || parts[0] == "." {
		return ""
	}
	return strings.Join(parts[:2], "/")
}

func githubActionsLocalReusableWorkflowPath(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	if at := strings.Index(trimmed, "@"); at >= 0 {
		trimmed = trimmed[:at]
	}
	trimmed = strings.TrimPrefix(trimmed, "./")
	trimmed = strings.TrimPrefix(trimmed, "/")
	if !strings.HasPrefix(trimmed, ".github/workflows/") {
		return ""
	}
	return trimmed
}
