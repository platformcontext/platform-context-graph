package query

import (
	"fmt"
	"net/http"
	"sort"
)

type traceDeploymentChainRequest struct {
	ServiceName               string `json:"service_name"`
	DirectOnly                bool   `json:"direct_only"`
	MaxDepth                  int    `json:"max_depth"`
	IncludeRelatedModuleUsage bool   `json:"include_related_module_usage"`
}

// traceDeploymentChain returns a story-first deployment trace for a service.
// POST /api/v0/impact/trace-deployment-chain
func (h *ImpactHandler) traceDeploymentChain(w http.ResponseWriter, r *http.Request) {
	var req traceDeploymentChainRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	if req.ServiceName == "" {
		WriteError(w, http.StatusBadRequest, "service_name is required")
		return
	}

	entityHandler := &EntityHandler{Neo4j: h.Neo4j}
	ctx, err := entityHandler.fetchWorkloadContext(r.Context(), "w.name = $service_name", map[string]any{"service_name": req.ServiceName})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if ctx == nil {
		WriteError(w, http.StatusNotFound, "service not found")
		return
	}

	WriteJSON(w, http.StatusOK, buildDeploymentTraceResponse(req.ServiceName, ctx))
}

func buildDeploymentTraceResponse(serviceName string, workloadContext map[string]any) map[string]any {
	instances, _ := workloadContext["instances"].([]map[string]any)
	platforms := distinctSortedInstanceField(instances, "platform_name")
	platformKinds := distinctSortedInstanceField(instances, "platform_kind")
	environments := distinctSortedInstanceField(instances, "environment")
	mappingMode := deploymentMappingMode(platformKinds)

	response := map[string]any{
		"service_name": serviceName,
		"workload_id":  safeStr(workloadContext, "id"),
		"name":         safeStr(workloadContext, "name"),
		"kind":         safeStr(workloadContext, "kind"),
		"repo_id":      safeStr(workloadContext, "repo_id"),
		"repo_name":    safeStr(workloadContext, "repo_name"),
		"subject": map[string]any{
			"type": "service",
			"id":   safeStr(workloadContext, "id"),
			"name": safeStr(workloadContext, "name"),
		},
		"instances":      instances,
		"story":          buildWorkloadStory(workloadContext),
		"story_sections": buildStorySections(platforms, platformKinds, environments),
		"deployment_overview": map[string]any{
			"instance_count":    len(instances),
			"environment_count": len(environments),
			"platform_count":    len(platforms),
			"platforms":         platforms,
			"platform_kinds":    platformKinds,
			"environments":      environments,
		},
		"controller_overview": buildControllerOverview(platforms, platformKinds),
		"gitops_overview":     buildGitOpsOverview(platforms, platformKinds),
		"runtime_overview":    buildRuntimeOverview(environments),
		"deployment_fact_summary": map[string]any{
			"instance_count":            len(instances),
			"environment_count":         len(environments),
			"platform_count":            len(platforms),
			"has_repository":            safeStr(workloadContext, "repo_id") != "",
			"mapping_mode":              mappingMode,
			"overall_confidence_reason": "platform_instances_observed",
		},
		"drilldowns": buildDeploymentDrilldowns(serviceName, safeStr(workloadContext, "id")),
	}

	return response
}

func buildStorySections(platforms, platformKinds, environments []string) []map[string]any {
	sections := []map[string]any{
		{
			"title":   "deployment",
			"summary": fmt.Sprintf("%d platform target(s) across %d environment(s)", len(platforms), len(environments)),
		},
	}
	if len(platformKinds) > 0 {
		sections = append(sections, map[string]any{
			"title":   "controllers",
			"summary": fmt.Sprintf("Observed controller families: %s", joinOrNone(platformKinds)),
		})
	}
	return sections
}

func buildControllerOverview(platforms, platformKinds []string) map[string]any {
	return map[string]any{
		"controller_count": len(platforms),
		"controllers":      platforms,
		"controller_kinds": platformKinds,
	}
}

func buildGitOpsOverview(platforms, platformKinds []string) map[string]any {
	enabled := false
	for _, kind := range platformKinds {
		if kind == "argocd_application" || kind == "argocd_applicationset" {
			enabled = true
			break
		}
	}
	return map[string]any{
		"enabled":          enabled,
		"tool_families":    platformKinds,
		"observed_targets": platforms,
	}
}

func buildRuntimeOverview(environments []string) map[string]any {
	return map[string]any{
		"environment_count": len(environments),
		"environments":      environments,
	}
}

func buildDeploymentDrilldowns(serviceName, workloadID string) map[string]any {
	return map[string]any{
		"service_context_path":  "/api/v0/services/" + serviceName + "/context",
		"service_story_path":    "/api/v0/services/" + serviceName + "/story",
		"workload_context_path": "/api/v0/workloads/" + workloadID + "/context",
	}
}

func deploymentMappingMode(platformKinds []string) string {
	for _, kind := range platformKinds {
		if kind == "argocd_application" || kind == "argocd_applicationset" {
			return "controller"
		}
	}
	if len(platformKinds) > 0 {
		return "evidence_only"
	}
	return "none"
}

func joinOrNone(values []string) string {
	if len(values) == 0 {
		return "none"
	}
	return fmt.Sprintf("%v", values)
}

func distinctSortedInstanceField(instances []map[string]any, key string) []string {
	values := make(map[string]struct{}, len(instances))
	for _, instance := range instances {
		value := safeStr(instance, key)
		if value == "" {
			continue
		}
		values[value] = struct{}{}
	}

	result := make([]string, 0, len(values))
	for value := range values {
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}
