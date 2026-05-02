package query

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
)

// fetchWorkloadContext queries graph-backed workload context with a custom
// WHERE clause and enriches linked repositories with local context evidence.
func (h *EntityHandler) fetchWorkloadContext(ctx context.Context, whereClause string, params map[string]any) (map[string]any, error) {
	return h.fetchWorkloadContextForOperation(ctx, whereClause, params, "workload_context")
}

// fetchServiceWorkloadContext avoids a backend-sensitive OR predicate by
// trying exact service-name lookup before exact workload-id lookup.
func (h *EntityHandler) fetchServiceWorkloadContext(ctx context.Context, serviceName string, operation string) (map[string]any, error) {
	serviceName = strings.TrimSpace(serviceName)
	if serviceName == "" {
		return nil, nil
	}
	result, err := h.fetchWorkloadContextForOperation(
		ctx,
		"w.name = $service_name",
		map[string]any{"service_name": serviceName},
		operation,
	)
	if err != nil || result != nil {
		return result, err
	}
	return h.fetchWorkloadContextForOperation(
		ctx,
		"w.id = $service_name",
		map[string]any{"service_name": serviceName},
		operation,
	)
}

// fetchWorkloadContextForOperation queries workload context and tags timing
// logs with the caller operation that will render the context.
func (h *EntityHandler) fetchWorkloadContextForOperation(ctx context.Context, whereClause string, params map[string]any, operation string) (map[string]any, error) {
	serviceName := StringVal(params, "service_name")
	if serviceName == "" {
		serviceName = StringVal(params, "workload_id")
	}
	if operation == "" {
		operation = "workload_context"
	}
	timer := startServiceQueryStage(ctx, h.Logger, operation, serviceName, "", "workload_lookup")
	baseCypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		RETURN w.id as id, w.name as name, w.kind as kind, w.repo_id as repo_id
		LIMIT 1
	`, whereClause)

	row, err := h.Neo4j.RunSingle(ctx, baseCypher, params)
	timer.Done(ctx, slog.Bool("found", row != nil))
	if err != nil {
		return nil, err
	}

	if row == nil {
		return nil, nil
	}

	followupWhereClause := whereClause
	followupParams := params
	if workloadID := StringVal(row, "id"); workloadID != "" {
		followupWhereClause = "w.id = $workload_id"
		followupParams = map[string]any{"workload_id": workloadID}
	}

	repoID := StringVal(row, "repo_id")
	timer = startServiceQueryStage(ctx, h.Logger, operation, StringVal(row, "name"), repoID, "repository_lookup")
	repoName := ""
	if repoID != "" {
		repoName, err = h.fetchRepositoryNameByID(ctx, repoID)
	} else {
		repoID, repoName, err = h.fetchWorkloadRepository(ctx, followupWhereClause, followupParams)
	}
	timer.Done(ctx, slog.String("resolved_repo_id", repoID))
	if err != nil {
		return nil, err
	}
	if repoName == "" {
		repoName = StringVal(row, "repo_name")
	}

	timer = startServiceQueryStage(ctx, h.Logger, operation, StringVal(row, "name"), repoID, "instance_lookup")
	instances, err := h.fetchWorkloadInstances(ctx, followupWhereClause, followupParams, repoID)
	timer.Done(ctx, slog.Int("row_count", len(instances)))
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
		timer = startServiceQueryStage(ctx, h.Logger, operation, StringVal(row, "name"), repoID, "repo_dependencies")
		result["dependencies"] = queryRepoDependencies(ctx, h.Neo4j, repoParams)
		timer.Done(ctx, slog.Int("row_count", len(mapSliceValue(result, "dependencies"))))
		timer = startServiceQueryStage(ctx, h.Logger, operation, StringVal(row, "name"), repoID, "repo_infrastructure")
		result["infrastructure"] = queryRepoInfrastructure(ctx, h.Neo4j, h.Content, repoParams)
		timer.Done(ctx, slog.Int("row_count", len(mapSliceValue(result, "infrastructure"))))
	}

	return result, nil
}

// fetchRepositoryNameByID uses the workload repo_id property as the selective
// anchor and avoids a relationship traversal on hot service read paths.
func (h *EntityHandler) fetchRepositoryNameByID(ctx context.Context, repoID string) (string, error) {
	cypher := `
		MATCH (r:Repository {id: $repo_id})
		RETURN r.name as repo_name
		LIMIT 1
	`
	row, err := h.Neo4j.RunSingle(ctx, cypher, map[string]any{"repo_id": repoID})
	if err != nil || row == nil {
		return "", err
	}
	return StringVal(row, "repo_name"), nil
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
func (h *EntityHandler) fetchWorkloadInstances(ctx context.Context, whereClause string, params map[string]any, repoID string) ([]map[string]any, error) {
	workloadID := StringVal(params, "workload_id")
	instanceCypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		MATCH (w)<-[:INSTANCE_OF]-(i:WorkloadInstance)
		RETURN i.id as instance_id,
		       i.environment as environment,
		       i.materialization_confidence as materialization_confidence,
		       i.materialization_provenance as materialization_provenance
		ORDER BY environment, instance_id
	`, whereClause)
	if workloadID != "" {
		instanceCypher = `
			MATCH (i:WorkloadInstance)
			WHERE i.workload_id = $workload_id
			RETURN i.id as instance_id,
			       i.environment as environment,
			       i.materialization_confidence as materialization_confidence,
			       i.materialization_provenance as materialization_provenance
			ORDER BY environment, instance_id
		`
	}
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
			"platforms":                  []map[string]any{},
			"environment":                StringVal(row, "environment"),
			"materialization_confidence": floatVal(row, "materialization_confidence"),
			"materialization_provenance": StringSliceVal(row, "materialization_provenance"),
			"platform_confidence":        0.0,
			"platform_reason":            "",
		}
		instances = append(instances, instance)
		byID[instanceID] = instance
	}

	provisionedRows, err := h.fetchProvisionedPlatformRows(ctx, repoID)
	if err != nil {
		return nil, err
	}
	if len(provisionedRows) == 1 {
		attachProvisionedPlatform(instances, provisionedRows[0])
		return instances, nil
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
	if workloadID != "" {
		platformCypher = `
			MATCH (i:WorkloadInstance)
			WHERE i.workload_id = $workload_id
			MATCH (i)-[runsOn:RUNS_ON]->(p:Platform)
			RETURN i.id as instance_id,
			       p.name as platform_name,
			       p.kind as platform_kind,
			       runsOn.confidence as platform_confidence,
			       runsOn.reason as platform_reason
			ORDER BY instance_id, platform_name
		`
	}
	platformRows, err := h.Neo4j.Run(ctx, platformCypher, params)
	if err != nil {
		return nil, err
	}
	for _, row := range platformRows {
		instance := byID[StringVal(row, "instance_id")]
		if instance == nil {
			continue
		}
		platform := map[string]any{
			"platform_name":       StringVal(row, "platform_name"),
			"platform_kind":       StringVal(row, "platform_kind"),
			"platform_confidence": floatVal(row, "platform_confidence"),
			"platform_reason":     StringVal(row, "platform_reason"),
		}
		instance["platforms"] = append(platformTargets(instance), platform)
		if StringVal(instance, "platform_name") == "" {
			instance["platform_name"] = platform["platform_name"]
			instance["platform_kind"] = platform["platform_kind"]
			instance["platform_confidence"] = platform["platform_confidence"]
			instance["platform_reason"] = platform["platform_reason"]
		}
	}

	return instances, nil
}

// fetchProvisionedPlatformRows uses repository-level platform evidence as a
// bounded alternative to expanding RUNS_ON from each workload instance.
func (h *EntityHandler) fetchProvisionedPlatformRows(ctx context.Context, repoID string) ([]map[string]any, error) {
	if h == nil || h.Neo4j == nil || strings.TrimSpace(repoID) == "" {
		return nil, nil
	}
	rows, err := h.Neo4j.Run(ctx, `
		MATCH (target:Repository {id: $repo_id})<-[rel:PROVISIONS_DEPENDENCY_FOR]-(repo:Repository)-[:PROVISIONS_PLATFORM]->(p:Platform)
		RETURN DISTINCT p.id as platform_id,
		       p.name as platform_name,
		       p.kind as platform_kind,
		       p.provider as platform_provider,
		       p.region as platform_region,
		       p.locator as platform_locator,
		       rel.confidence as platform_confidence,
		       rel.reason as platform_reason
		ORDER BY platform_name, platform_id
	`, map[string]any{"repo_id": repoID})
	if err != nil {
		return nil, err
	}
	return rows, nil
}

// attachProvisionedPlatform applies one unambiguous provisioned platform to
// all materialized workload instances for the service.
func attachProvisionedPlatform(instances []map[string]any, row map[string]any) {
	platform := map[string]any{
		"platform_name":       StringVal(row, "platform_name"),
		"platform_kind":       StringVal(row, "platform_kind"),
		"platform_confidence": floatVal(row, "platform_confidence"),
		"platform_reason":     StringVal(row, "platform_reason"),
	}
	for _, instance := range instances {
		instance["platforms"] = []map[string]any{platform}
		instance["platform_name"] = platform["platform_name"]
		instance["platform_kind"] = platform["platform_kind"]
		instance["platform_confidence"] = platform["platform_confidence"]
		instance["platform_reason"] = platform["platform_reason"]
	}
}
