package query

import (
	"context"
	"fmt"
	"net/http"
	"sort"
	"strings"
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
	if workloadID := safeStr(ctx, "id"); workloadID != "" {
		deploymentSources, err := h.fetchDeploymentSources(r.Context(), workloadID, safeStr(ctx, "repo_id"))
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query deployment sources: %v", err))
			return
		}
		cloudResources, err := h.fetchCloudResources(r.Context(), workloadID)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query cloud resources: %v", err))
			return
		}
		k8sResources, imageRefs, err := h.fetchK8sResources(r.Context(), safeStr(ctx, "repo_id"), safeStr(ctx, "name"))
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query k8s resources: %v", err))
			return
		}
		controllerEntities, err := h.fetchControllerEntities(r.Context(), deploymentSources)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query controller entities: %v", err))
			return
		}
		ctx["deployment_sources"] = deploymentSources
		ctx["cloud_resources"] = cloudResources
		ctx["k8s_resources"] = k8sResources
		ctx["image_refs"] = imageRefs
		ctx["controller_entities"] = controllerEntities
	}

	WriteJSON(w, http.StatusOK, buildDeploymentTraceResponse(req.ServiceName, ctx))
}

func buildDeploymentTraceResponse(serviceName string, workloadContext map[string]any) map[string]any {
	instances, _ := workloadContext["instances"].([]map[string]any)
	deploymentSources, _ := workloadContext["deployment_sources"].([]map[string]any)
	cloudResources, _ := workloadContext["cloud_resources"].([]map[string]any)
	k8sResources, _ := workloadContext["k8s_resources"].([]map[string]any)
	imageRefs, _ := workloadContext["image_refs"].([]string)
	controllerEntities, _ := workloadContext["controller_entities"].([]map[string]any)
	k8sRelationships := buildK8sRelationships(k8sResources)
	platforms := distinctSortedInstanceField(instances, "platform_name")
	platformKinds := distinctSortedInstanceField(instances, "platform_kind")
	environments := distinctSortedInstanceField(instances, "environment")
	mappingMode := deploymentMappingMode(platformKinds)
	deploymentFacts := buildDeploymentFacts(platforms, platformKinds, environments, deploymentSources)
	story := buildWorkloadStory(workloadContext)
	if provenanceStory := buildDeploymentProvenanceStory(controllerEntities, deploymentSources); provenanceStory != "" {
		story = story + " " + provenanceStory
	}

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
		"instances":               instances,
		"deployment_sources":      deploymentSources,
		"cloud_resources":         cloudResources,
		"k8s_resources":           k8sResources,
		"image_refs":              imageRefs,
		"k8s_relationships":       k8sRelationships,
		"deployment_facts":        deploymentFacts,
		"controller_driven_paths": buildControllerDrivenPaths(platforms, platformKinds),
		"delivery_paths":          buildDeliveryPaths(deploymentSources, cloudResources, k8sResources, imageRefs, k8sRelationships),
		"story":                   story,
		"story_sections":          buildStorySections(platforms, platformKinds, environments),
		"deployment_overview": map[string]any{
			"instance_count":          len(instances),
			"environment_count":       len(environments),
			"platform_count":          len(platforms),
			"deployment_source_count": len(deploymentSources),
			"cloud_resource_count":    len(cloudResources),
			"k8s_resource_count":      len(k8sResources),
			"image_ref_count":         len(imageRefs),
			"platforms":               platforms,
			"platform_kinds":          platformKinds,
			"environments":            environments,
		},
		"controller_overview": buildControllerOverview(platforms, platformKinds, controllerEntities),
		"gitops_overview":     buildGitOpsOverview(platforms, platformKinds),
		"runtime_overview":    buildRuntimeOverview(environments),
		"deployment_fact_summary": map[string]any{
			"instance_count":            len(instances),
			"environment_count":         len(environments),
			"platform_count":            len(platforms),
			"deployment_source_count":   len(deploymentSources),
			"cloud_resource_count":      len(cloudResources),
			"k8s_resource_count":        len(k8sResources),
			"image_ref_count":           len(imageRefs),
			"fact_count":                len(deploymentFacts),
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

func buildDeploymentFacts(
	platforms []string,
	platformKinds []string,
	environments []string,
	deploymentSources []map[string]any,
) []map[string]any {
	facts := make([]map[string]any, 0, len(platforms)+len(environments)+len(deploymentSources))
	for i, platform := range platforms {
		fact := map[string]any{
			"type":       "RUNS_ON_PLATFORM",
			"target":     platform,
			"confidence": 1.0,
		}
		if i < len(platformKinds) {
			fact["kind"] = platformKinds[i]
		}
		facts = append(facts, fact)
	}
	for _, environment := range environments {
		facts = append(facts, map[string]any{
			"type":       "OBSERVED_IN_ENVIRONMENT",
			"target":     environment,
			"confidence": 1.0,
		})
	}
	for _, source := range deploymentSources {
		facts = append(facts, map[string]any{
			"type":       "DEPLOYS_FROM",
			"target":     safeStr(source, "repo_name"),
			"target_id":  safeStr(source, "repo_id"),
			"confidence": floatVal(source, "confidence"),
			"reason":     safeStr(source, "reason"),
		})
	}
	return facts
}

func buildControllerDrivenPaths(platforms, platformKinds []string) []map[string]any {
	paths := make([]map[string]any, 0, len(platforms))
	for i, platform := range platforms {
		path := map[string]any{
			"controller": platform,
		}
		if i < len(platformKinds) && platformKinds[i] != "" {
			path["controller_kind"] = platformKinds[i]
		}
		paths = append(paths, path)
	}
	return paths
}

func buildDeliveryPaths(
	deploymentSources []map[string]any,
	cloudResources []map[string]any,
	k8sResources []map[string]any,
	imageRefs []string,
	k8sRelationships []map[string]any,
) []map[string]any {
	paths := make([]map[string]any, 0, len(deploymentSources)+len(cloudResources)+len(k8sResources)+len(imageRefs)+len(k8sRelationships))
	for _, source := range deploymentSources {
		paths = append(paths, map[string]any{
			"type":       "deployment_source",
			"target":     safeStr(source, "repo_name"),
			"target_id":  safeStr(source, "repo_id"),
			"confidence": floatVal(source, "confidence"),
		})
	}
	for _, resource := range cloudResources {
		paths = append(paths, map[string]any{
			"type":       "cloud_resource",
			"target":     safeStr(resource, "name"),
			"target_id":  safeStr(resource, "id"),
			"confidence": floatVal(resource, "confidence"),
		})
	}
	for _, resource := range k8sResources {
		paths = append(paths, map[string]any{
			"type":      "k8s_resource",
			"target":    safeStr(resource, "entity_name"),
			"target_id": safeStr(resource, "entity_id"),
			"kind":      safeStr(resource, "kind"),
		})
	}
	for _, imageRef := range imageRefs {
		paths = append(paths, map[string]any{
			"type":   "image_ref",
			"target": imageRef,
		})
	}
	for _, relationship := range k8sRelationships {
		paths = append(paths, map[string]any{
			"type":        "k8s_relationship",
			"target":      safeStr(relationship, "target_name"),
			"target_id":   safeStr(relationship, "target_id"),
			"source_name": safeStr(relationship, "source_name"),
			"reason":      safeStr(relationship, "reason"),
			"kind":        safeStr(relationship, "type"),
		})
	}
	return paths
}

func buildDeploymentDrilldowns(serviceName, workloadID string) map[string]any {
	return map[string]any{
		"service_context_path":  "/api/v0/services/" + serviceName + "/context",
		"service_story_path":    "/api/v0/services/" + serviceName + "/story",
		"workload_context_path": "/api/v0/workloads/" + workloadID + "/context",
	}
}

func buildDeploymentProvenanceStory(controllerEntities, deploymentSources []map[string]any) string {
	parts := make([]string, 0, 2)
	if len(controllerEntities) > 0 {
		summaries := make([]string, 0, len(controllerEntities))
		for _, controller := range controllerEntities {
			summary := StringVal(controller, "entity_name")
			if summary == "" {
				summary = StringVal(controller, "entity_id")
			}
			if controllerKind := StringVal(controller, "controller_kind"); controllerKind != "" {
				summary += " (" + controllerKind + ")"
			}
			if sourceRepo := StringVal(controller, "source_repo"); sourceRepo != "" {
				summary += " from " + sourceRepo
			}
			summaries = append(summaries, summary)
		}
		parts = append(parts, "Controller provenance: "+joinSentenceFragments(summaries)+".")
	}
	if len(deploymentSources) > 0 {
		summaries := make([]string, 0, len(deploymentSources))
		for _, source := range deploymentSources {
			summary := StringVal(source, "repo_name")
			if summary == "" {
				summary = StringVal(source, "repo_id")
			}
			if reason := StringVal(source, "reason"); reason != "" {
				summary += " via " + reason
			}
			summaries = append(summaries, summary)
		}
		parts = append(parts, "Deployment sources: "+joinSentenceFragments(summaries)+".")
	}
	return strings.Join(parts, " ")
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

func (h *ImpactHandler) fetchDeploymentSources(
	ctx context.Context,
	workloadID string,
	repoID string,
) ([]map[string]any, error) {
	if h == nil || h.Neo4j == nil {
		return nil, nil
	}
	return fetchDeploymentSourcesFromGraph(ctx, h.Neo4j, workloadID, repoID)
}

func fetchDeploymentSourcesFromGraph(
	ctx context.Context,
	reader GraphReader,
	workloadID string,
	repoID string,
) ([]map[string]any, error) {
	rows, err := reader.Run(ctx, `
		CALL {
			MATCH (w:Workload {id: $workload_id})<-[:INSTANCE_OF]-(i:WorkloadInstance)-[rel:DEPLOYMENT_SOURCE]->(repo:Repository)
			RETURN repo.id as repo_id, repo.name as repo_name, rel.confidence as confidence, rel.reason as reason
			UNION
			MATCH (targetRepo:Repository {id: $repo_id})<-[rel:DEPLOYS_FROM]-(repo:Repository)
			RETURN repo.id as repo_id, repo.name as repo_name, rel.confidence as confidence, coalesce(rel.reason, rel.evidence_type, 'repository_deploys_from') as reason
		}
		RETURN DISTINCT repo_id, repo_name, confidence, reason
		ORDER BY repo_name
	`, map[string]any{
		"workload_id": workloadID,
		"repo_id":     repoID,
	})
	if err != nil {
		return nil, err
	}
	sources := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		sources = append(sources, map[string]any{
			"repo_id":    StringVal(row, "repo_id"),
			"repo_name":  StringVal(row, "repo_name"),
			"confidence": floatVal(row, "confidence"),
			"reason":     StringVal(row, "reason"),
		})
	}
	return sources, nil
}

func (h *ImpactHandler) fetchCloudResources(ctx context.Context, workloadID string) ([]map[string]any, error) {
	rows, err := h.Neo4j.Run(ctx, `
		MATCH (w:Workload {id: $workload_id})<-[:INSTANCE_OF]-(i:WorkloadInstance)-[rel:USES]->(c:CloudResource)
		RETURN DISTINCT c.id as id, c.name as name, c.kind as kind, c.provider as provider, c.environment as environment,
		       rel.confidence as confidence, rel.reason as reason
		ORDER BY c.name
	`, map[string]any{"workload_id": workloadID})
	if err != nil {
		return nil, err
	}
	resources := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		resources = append(resources, map[string]any{
			"id":          StringVal(row, "id"),
			"name":        StringVal(row, "name"),
			"kind":        StringVal(row, "kind"),
			"provider":    StringVal(row, "provider"),
			"environment": StringVal(row, "environment"),
			"confidence":  floatVal(row, "confidence"),
			"reason":      StringVal(row, "reason"),
		})
	}
	return resources, nil
}

func (h *ImpactHandler) fetchK8sResources(
	ctx context.Context,
	repoID string,
	workloadName string,
) ([]map[string]any, []string, error) {
	if h == nil || h.Content == nil || repoID == "" || workloadName == "" {
		return nil, nil, nil
	}

	rows, err := h.Content.SearchEntitiesByName(ctx, repoID, "K8sResource", workloadName, 50)
	if err != nil {
		return nil, nil, err
	}

	resources := make([]map[string]any, 0, len(rows))
	imageSet := make(map[string]struct{})
	for _, row := range rows {
		if row.EntityName != workloadName {
			continue
		}
		kind, _ := metadataNonEmptyString(row.Metadata, "kind")
		qualifiedName, _ := metadataNonEmptyString(row.Metadata, "qualified_name")
		images := metadataStringSlice(row.Metadata, "container_images")
		for _, image := range images {
			imageSet[image] = struct{}{}
		}
		resources = append(resources, map[string]any{
			"entity_id":        row.EntityID,
			"entity_name":      row.EntityName,
			"kind":             kind,
			"qualified_name":   qualifiedName,
			"relative_path":    row.RelativePath,
			"container_images": images,
		})
	}

	imageRefs := make([]string, 0, len(imageSet))
	for image := range imageSet {
		imageRefs = append(imageRefs, image)
	}
	sort.Strings(imageRefs)
	return resources, imageRefs, nil
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
