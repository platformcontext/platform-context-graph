package main

import (
	"context"

	"github.com/platformcontext/platform-context-graph/go/internal/query"
	"github.com/platformcontext/platform-context-graph/go/internal/reducer"
)

type neo4jWorkloadDependencyLookup struct {
	reader query.GraphReader
}

func (l neo4jWorkloadDependencyLookup) ListRepoDependencyEdges(
	ctx context.Context,
	repoIDs []string,
) ([]reducer.RepoDependencyEdge, error) {
	if l.reader == nil || len(repoIDs) == 0 {
		return nil, nil
	}

	rows, err := l.reader.Run(ctx, `
		MATCH (source:Repository)-[:DEPENDS_ON]->(target:Repository)
		WHERE source.id IN $repo_ids OR target.id IN $repo_ids
		RETURN DISTINCT source.id AS source_repo_id, target.id AS target_repo_id
	`, map[string]any{"repo_ids": repoIDs})
	if err != nil {
		return nil, err
	}

	edges := make([]reducer.RepoDependencyEdge, 0, len(rows))
	for _, row := range rows {
		sourceRepoID := query.StringVal(row, "source_repo_id")
		targetRepoID := query.StringVal(row, "target_repo_id")
		if sourceRepoID == "" || targetRepoID == "" {
			continue
		}
		edges = append(edges, reducer.RepoDependencyEdge{
			SourceRepoID: sourceRepoID,
			TargetRepoID: targetRepoID,
		})
	}
	return edges, nil
}

func (l neo4jWorkloadDependencyLookup) ListRepoWorkloads(
	ctx context.Context,
	repoIDs []string,
) ([]reducer.RepoWorkload, error) {
	if l.reader == nil || len(repoIDs) == 0 {
		return nil, nil
	}

	rows, err := l.reader.Run(ctx, `
		MATCH (repo:Repository)-[:DEFINES]->(workload:Workload)
		WHERE repo.id IN $repo_ids
		RETURN DISTINCT repo.id AS repo_id, workload.id AS workload_id
	`, map[string]any{"repo_ids": repoIDs})
	if err != nil {
		return nil, err
	}

	workloads := make([]reducer.RepoWorkload, 0, len(rows))
	for _, row := range rows {
		repoID := query.StringVal(row, "repo_id")
		workloadID := query.StringVal(row, "workload_id")
		if repoID == "" || workloadID == "" {
			continue
		}
		workloads = append(workloads, reducer.RepoWorkload{
			RepoID:     repoID,
			WorkloadID: workloadID,
		})
	}
	return workloads, nil
}
