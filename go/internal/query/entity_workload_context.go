package query

import (
	"context"
	"fmt"
)

// fetchWorkloadContext queries graph-backed workload context with a custom
// WHERE clause and enriches linked repositories with local context evidence.
func (h *EntityHandler) fetchWorkloadContext(ctx context.Context, whereClause string, params map[string]any) (map[string]any, error) {
	baseCypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		RETURN w.id as id, w.name as name, w.kind as kind
		LIMIT 1
	`, whereClause)

	row, err := h.Neo4j.RunSingle(ctx, baseCypher, params)
	if err != nil {
		return nil, err
	}

	if row == nil {
		return nil, nil
	}

	repoID, repoName, err := h.fetchWorkloadRepository(ctx, whereClause, params)
	if err != nil {
		return nil, err
	}
	if repoID == "" {
		repoID = StringVal(row, "repo_id")
	}
	if repoName == "" {
		repoName = StringVal(row, "repo_name")
	}

	instances, err := h.fetchWorkloadInstances(ctx, whereClause, params)
	if err != nil {
		return nil, err
	}
	if len(instances) == 0 {
		instances = extractInstances(row)
	}

	result := map[string]any{
		"id":        StringVal(row, "id"),
		"name":      StringVal(row, "name"),
		"kind":      StringVal(row, "kind"),
		"repo_id":   repoID,
		"repo_name": repoName,
		"instances": instances,
	}

	if repoID != "" {
		repoParams := map[string]any{"repo_id": repoID}
		result["dependencies"] = queryRepoDependencies(ctx, h.Neo4j, repoParams)
		result["infrastructure"] = queryRepoInfrastructure(ctx, h.Neo4j, h.Content, repoParams)
		result["entry_points"] = queryRepoEntryPoints(ctx, h.Neo4j, repoParams)
	}

	return result, nil
}

// fetchWorkloadRepository resolves the repository link without OPTIONAL MATCH,
// avoiding backend-specific projection behavior in graph read paths.
func (h *EntityHandler) fetchWorkloadRepository(ctx context.Context, whereClause string, params map[string]any) (string, string, error) {
	cypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		MATCH (r:Repository)-[:DEFINES]->(w)
		RETURN r.id as repo_id, r.name as repo_name
		LIMIT 1
	`, whereClause)
	rows, err := h.Neo4j.Run(ctx, cypher, params)
	if err != nil {
		return "", "", err
	}
	if len(rows) == 0 {
		return "", "", nil
	}
	return StringVal(rows[0], "repo_id"), StringVal(rows[0], "repo_name"), nil
}

// fetchWorkloadInstances assembles instance and platform fields from scalar
// rows so query surfaces do not depend on backend map-projection semantics.
func (h *EntityHandler) fetchWorkloadInstances(ctx context.Context, whereClause string, params map[string]any) ([]map[string]any, error) {
	instanceCypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		MATCH (w)<-[:INSTANCE_OF]-(i:WorkloadInstance)
		RETURN i.id as instance_id,
		       i.environment as environment,
		       i.materialization_confidence as materialization_confidence,
		       i.materialization_provenance as materialization_provenance
		ORDER BY environment, instance_id
	`, whereClause)
	instanceRows, err := h.Neo4j.Run(ctx, instanceCypher, params)
	if err != nil {
		return nil, err
	}
	if len(instanceRows) == 0 {
		return []map[string]any{}, nil
	}

	instances := make([]map[string]any, 0, len(instanceRows))
	byID := make(map[string]map[string]any, len(instanceRows))
	for _, row := range instanceRows {
		instanceID := StringVal(row, "instance_id")
		if instanceID == "" {
			continue
		}
		instance := map[string]any{
			"instance_id":                instanceID,
			"platform_name":              "",
			"platform_kind":              "",
			"environment":                StringVal(row, "environment"),
			"materialization_confidence": floatVal(row, "materialization_confidence"),
			"materialization_provenance": StringSliceVal(row, "materialization_provenance"),
			"platform_confidence":        0.0,
			"platform_reason":            "",
		}
		instances = append(instances, instance)
		byID[instanceID] = instance
	}

	platformCypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		MATCH (w)<-[:INSTANCE_OF]-(i:WorkloadInstance)
		MATCH (i)-[runsOn:RUNS_ON]->(p:Platform)
		RETURN i.id as instance_id,
		       p.name as platform_name,
		       p.kind as platform_kind,
		       runsOn.confidence as platform_confidence,
		       runsOn.reason as platform_reason
		ORDER BY instance_id, platform_name
	`, whereClause)
	platformRows, err := h.Neo4j.Run(ctx, platformCypher, params)
	if err != nil {
		return nil, err
	}
	for _, row := range platformRows {
		instance := byID[StringVal(row, "instance_id")]
		if instance == nil || StringVal(instance, "platform_name") != "" {
			continue
		}
		instance["platform_name"] = StringVal(row, "platform_name")
		instance["platform_kind"] = StringVal(row, "platform_kind")
		instance["platform_confidence"] = floatVal(row, "platform_confidence")
		instance["platform_reason"] = StringVal(row, "platform_reason")
	}

	return instances, nil
}
