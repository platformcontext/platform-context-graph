package query

import "context"

func loadDeploymentArtifactOverview(
	ctx context.Context,
	graph GraphReader,
	content *ContentReader,
	repoID string,
	repoName string,
	files []FileContent,
	overview map[string]any,
) (map[string]any, error) {
	merged := overview
	var firstErr error

	configArtifacts, err := loadSharedRepositoryConfigArtifacts(
		ctx,
		graph,
		content,
		repoID,
		repoName,
		files,
	)
	if err != nil && firstErr == nil {
		firstErr = err
	} else {
		merged = mergeArtifactOverview(merged, configArtifacts)
	}

	runtimeArtifacts, err := loadRepositoryRuntimeArtifacts(ctx, content, repoID, files)
	if err != nil && firstErr == nil {
		firstErr = err
	} else {
		merged = mergeArtifactOverview(merged, runtimeArtifacts)
	}

	workflowArtifacts, err := loadRepositoryWorkflowArtifacts(ctx, content, repoID, files)
	if err != nil && firstErr == nil {
		firstErr = err
	} else {
		merged = mergeArtifactOverview(merged, workflowArtifacts)
	}

	return merged, firstErr
}

func mergeArtifactOverview(overview map[string]any, artifacts map[string]any) map[string]any {
	if len(artifacts) == 0 {
		return overview
	}
	if overview == nil {
		overview = map[string]any{}
	}
	overview["deployment_artifacts"] = mergeDeploymentArtifactMaps(
		mapValue(overview, "deployment_artifacts"),
		artifacts,
	)
	return overview
}
