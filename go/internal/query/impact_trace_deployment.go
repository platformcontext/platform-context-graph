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

	response := map[string]any{
		"service_name": serviceName,
		"workload_id":  safeStr(workloadContext, "id"),
		"name":         safeStr(workloadContext, "name"),
		"kind":         safeStr(workloadContext, "kind"),
		"repo_id":      safeStr(workloadContext, "repo_id"),
		"repo_name":    safeStr(workloadContext, "repo_name"),
		"instances":    instances,
		"story":        buildWorkloadStory(workloadContext),
		"deployment_overview": map[string]any{
			"instance_count":    len(instances),
			"environment_count": len(environments),
			"platform_count":    len(platforms),
			"platforms":         platforms,
			"platform_kinds":    platformKinds,
			"environments":      environments,
		},
		"deployment_fact_summary": map[string]any{
			"instance_count":    len(instances),
			"environment_count": len(environments),
			"platform_count":    len(platforms),
			"has_repository":    safeStr(workloadContext, "repo_id") != "",
		},
	}

	return response
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
