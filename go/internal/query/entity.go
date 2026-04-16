package query

import (
	"context"
	"fmt"
	"net/http"
)

// EntityHandler exposes HTTP routes for entity queries.
type EntityHandler struct {
	Neo4j   GraphReader
	Content *ContentReader
}

// Mount registers all entity routes on the given mux.
func (h *EntityHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/entities/resolve", h.resolveEntity)
	mux.HandleFunc("GET /api/v0/entities/{entity_id}/context", h.getEntityContext)
	mux.HandleFunc("GET /api/v0/workloads/{workload_id}/context", h.getWorkloadContext)
	mux.HandleFunc("GET /api/v0/workloads/{workload_id}/story", h.getWorkloadStory)
	mux.HandleFunc("GET /api/v0/services/{service_name}/context", h.getServiceContext)
	mux.HandleFunc("GET /api/v0/services/{service_name}/story", h.getServiceStory)
}

// resolveEntityRequest is the request body for entity resolution.
type resolveEntityRequest struct {
	Name   string `json:"name"`
	Type   string `json:"type"`
	RepoID string `json:"repo_id"`
}

// resolveEntity resolves an entity by name and optional type/repo filters.
func (h *EntityHandler) resolveEntity(w http.ResponseWriter, r *http.Request) {
	var req resolveEntityRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Name == "" {
		WriteError(w, http.StatusBadRequest, "name is required")
		return
	}

	cypher := `MATCH (e) WHERE e.name = $name`
	params := map[string]any{"name": req.Name}

	if req.Type != "" {
		graphLabel, semanticKey, semanticValue, ok := resolveGraphEntityType(req.Type)
		if ok {
			cypher += " AND $type IN labels(e)"
			params["type"] = graphLabel
			if semanticKey != "" {
				cypher += fmt.Sprintf(" AND coalesce(e.%s, '') = $semantic_filter", semanticKey)
				params["semantic_filter"] = semanticValue
			}
		}
	}

	if req.RepoID != "" {
		cypher += `
			AND EXISTS {
				MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
				WHERE r.id = $repo_id
			}
		`
		params["repo_id"] = req.RepoID
	}

	cypher += `
		OPTIONAL MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		RETURN e.id as id, labels(e) as labels, e.name as name,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
		       e.annotation_kind as annotation_kind,
		       e.context as context
		ORDER BY e.name
		LIMIT 20
	`

	var rows []map[string]any
	var err error
	if h.Neo4j != nil {
		rows, err = h.Neo4j.Run(r.Context(), cypher, params)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
			return
		}
	}

	entities := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		entity := map[string]any{
			"id":         StringVal(row, "id"),
			"labels":     StringSliceVal(row, "labels"),
			"name":       StringVal(row, "name"),
			"file_path":  StringVal(row, "file_path"),
			"repo_id":    StringVal(row, "repo_id"),
			"repo_name":  StringVal(row, "repo_name"),
			"language":   StringVal(row, "language"),
			"start_line": IntVal(row, "start_line"),
			"end_line":   IntVal(row, "end_line"),
		}
		if metadata := graphResultMetadata(row); len(metadata) > 0 {
			entity["metadata"] = metadata
		}
		entities = append(entities, entity)
	}
	entities, err = h.enrichEntityResultsWithContentMetadata(r.Context(), entities, req.RepoID, req.Name, 20)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("enrich entities: %v", err))
		return
	}
	for i := range entities {
		attachSemanticSummary(entities[i])
	}
	if len(entities) == 0 {
		entities, err = h.resolveEntityFromContent(r.Context(), req.Name, req.Type, req.RepoID, 20)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("resolve content entities: %v", err))
			return
		}
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"entities": entities,
		"count":    len(entities),
	})
}

// getEntityContext retrieves the context for a specific entity.
func (h *EntityHandler) getEntityContext(w http.ResponseWriter, r *http.Request) {
	entityID := PathParam(r, "entity_id")
	if entityID == "" {
		WriteError(w, http.StatusBadRequest, "entity_id is required")
		return
	}

	cypher := `
		MATCH (e) WHERE e.id = $entity_id
		OPTIONAL MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		OPTIONAL MATCH (e)-[rel]->(target)
		RETURN e.id as id, labels(e) as labels, e.name as name,
		       f.relative_path as file_path,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
		       e.annotation_kind as annotation_kind,
		       e.context as context,
		       e.docstring as docstring,
		       e.method_kind as method_kind,
		       r.id as repo_id, r.name as repo_name,
		       collect(DISTINCT {type: type(rel), target_name: target.name, target_id: target.id}) as relationships
	`

	params := map[string]any{"entity_id": entityID}
	var row map[string]any
	var err error
	if h.Neo4j != nil {
		row, err = h.Neo4j.RunSingle(r.Context(), cypher, params)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
			return
		}
	}

	if row == nil {
		response, fallbackErr := h.getEntityContextFromContent(r.Context(), entityID)
		if fallbackErr != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", fallbackErr))
			return
		}
		if response == nil {
			WriteError(w, http.StatusNotFound, "entity not found")
			return
		}
		WriteJSON(w, http.StatusOK, response)
		return
	}

	response := map[string]any{
		"id":            StringVal(row, "id"),
		"labels":        StringSliceVal(row, "labels"),
		"name":          StringVal(row, "name"),
		"file_path":     StringVal(row, "file_path"),
		"repo_id":       StringVal(row, "repo_id"),
		"repo_name":     StringVal(row, "repo_name"),
		"language":      StringVal(row, "language"),
		"start_line":    IntVal(row, "start_line"),
		"end_line":      IntVal(row, "end_line"),
		"relationships": extractRelationships(row),
	}
	if metadata := graphResultMetadata(row); len(metadata) > 0 {
		response["metadata"] = metadata
	}
	enriched, err := h.enrichEntityResultsWithContentMetadata(r.Context(), []map[string]any{response}, StringVal(row, "repo_id"), StringVal(row, "name"), 1)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("enrich entity context: %v", err))
		return
	}
	response = enriched[0]
	attachSemanticSummary(response)

	WriteJSON(w, http.StatusOK, response)
}

func (h *EntityHandler) resolveEntityFromContent(
	ctx context.Context,
	name string,
	typeName string,
	repoID string,
	limit int,
) ([]map[string]any, error) {
	if h == nil || h.Content == nil || repoID == "" || name == "" {
		return nil, nil
	}

	entityType := contentEntityTypeForResolve(typeName)
	rows, err := h.Content.SearchEntitiesByName(ctx, repoID, entityType, name, limit)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		results = append(results, contentEntityToMap(row))
	}
	return results, nil
}

func (h *EntityHandler) getEntityContextFromContent(ctx context.Context, entityID string) (map[string]any, error) {
	if h == nil || h.Content == nil || entityID == "" {
		return nil, nil
	}

	entity, err := h.Content.GetEntityContent(ctx, entityID)
	if err != nil || entity == nil {
		return nil, err
	}

	response := contentEntityToMap(*entity)
	relationshipSet, err := buildContentRelationshipSet(ctx, h.Content, *entity)
	if err != nil {
		return nil, err
	}
	relationships := append([]map[string]any{}, relationshipSet.incoming...)
	relationships = append(relationships, relationshipSet.outgoing...)
	response["relationships"] = relationships
	attachSemanticSummary(response)
	return response, nil
}

func contentEntityTypeForResolve(typeName string) string {
	if typeName == "" {
		return ""
	}
	if entityType, ok := resolveContentBackedEntityTypes[typeName]; ok {
		return entityType
	}
	if entityType, ok := contentBackedEntityTypes[typeName]; ok {
		return entityType
	}
	if entityType, ok := graphBackedEntityTypes[typeName]; ok {
		return entityType
	}
	return typeName
}

func resolveGraphEntityType(typeName string) (string, string, string, bool) {
	if graphLabel, semanticKey, semanticValue, ok := elixirGraphSemanticEntityType(typeName); ok {
		return graphLabel, semanticKey, semanticValue, true
	}
	if graphLabel, ok := graphBackedEntityTypes[typeName]; ok {
		return graphLabel, "", "", true
	}
	if graphLabel, ok := graphFirstContentBackedEntityTypes[typeName]; ok {
		return graphLabel, "", "", true
	}
	return "", "", "", false
}

var resolveContentBackedEntityTypes = map[string]string{
	"analytics_model":          "AnalyticsModel",
	"annotation":               "Annotation",
	"argocd_application":       "ArgoCDApplication",
	"argocd_applicationset":    "ArgoCDApplicationSet",
	"component":                "Component",
	"cloudformation_condition": "CloudFormationCondition",
	"cloudformation_export":    "CloudFormationExport",
	"cloudformation_import":    "CloudFormationImport",
	"cloudformation_output":    "CloudFormationOutput",
	"cloudformation_parameter": "CloudFormationParameter",
	"cloudformation_resource":  "CloudFormationResource",
	"data_asset":               "DataAsset",
	"impl_block":               "ImplBlock",
	"k8s_resource":             "K8sResource",
	"kustomize_overlay":        "KustomizeOverlay",
	"protocol":                 "Protocol",
	"terraform_block":          "TerraformBlock",
	"terragrunt_dependency":    "TerragruntDependency",
	"terragrunt_input":         "TerragruntInput",
	"terragrunt_local":         "TerragruntLocal",
	"type_alias":               "TypeAlias",
	"type_annotation":          "TypeAnnotation",
	"typedef":                  "Typedef",
	"guard":                    "guard",
	"protocol_implementation":  "ProtocolImplementation",
	"module_attribute":         "module_attribute",
}

func contentEntityToMap(entity EntityContent) map[string]any {
	result := map[string]any{
		"id":         entity.EntityID,
		"entity_id":  entity.EntityID,
		"name":       entity.EntityName,
		"labels":     []string{entity.EntityType},
		"file_path":  entity.RelativePath,
		"repo_id":    entity.RepoID,
		"language":   entity.Language,
		"start_line": entity.StartLine,
		"end_line":   entity.EndLine,
		"metadata":   entity.Metadata,
	}
	attachSemanticSummary(result)
	return result
}

// getWorkloadContext retrieves the context for a specific workload.
func (h *EntityHandler) getWorkloadContext(w http.ResponseWriter, r *http.Request) {
	workloadID := PathParam(r, "workload_id")
	if workloadID == "" {
		WriteError(w, http.StatusBadRequest, "workload_id is required")
		return
	}

	ctx, err := h.fetchWorkloadContext(r.Context(), "w.id = $workload_id", map[string]any{"workload_id": workloadID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}

	if ctx == nil {
		WriteError(w, http.StatusNotFound, "workload not found")
		return
	}

	WriteJSON(w, http.StatusOK, ctx)
}

// getWorkloadStory retrieves a narrative summary for a workload.
func (h *EntityHandler) getWorkloadStory(w http.ResponseWriter, r *http.Request) {
	workloadID := PathParam(r, "workload_id")
	if workloadID == "" {
		WriteError(w, http.StatusBadRequest, "workload_id is required")
		return
	}

	ctx, err := h.fetchWorkloadContext(r.Context(), "w.id = $workload_id", map[string]any{"workload_id": workloadID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}

	if ctx == nil {
		WriteError(w, http.StatusNotFound, "workload not found")
		return
	}

	story := buildWorkloadStory(ctx)
	WriteJSON(w, http.StatusOK, map[string]any{
		"workload_id": workloadID,
		"name":        ctx["name"],
		"story":       story,
	})
}

// getServiceContext retrieves the context for a service by name.
func (h *EntityHandler) getServiceContext(w http.ResponseWriter, r *http.Request) {
	serviceName := PathParam(r, "service_name")
	if serviceName == "" {
		WriteError(w, http.StatusBadRequest, "service_name is required")
		return
	}

	ctx, err := h.fetchWorkloadContext(r.Context(), "w.name = $service_name", map[string]any{"service_name": serviceName})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}

	if ctx == nil {
		WriteError(w, http.StatusNotFound, "service not found")
		return
	}

	WriteJSON(w, http.StatusOK, ctx)
}

// getServiceStory retrieves a narrative summary for a service.
func (h *EntityHandler) getServiceStory(w http.ResponseWriter, r *http.Request) {
	serviceName := PathParam(r, "service_name")
	if serviceName == "" {
		WriteError(w, http.StatusBadRequest, "service_name is required")
		return
	}

	ctx, err := h.fetchWorkloadContext(r.Context(), "w.name = $service_name", map[string]any{"service_name": serviceName})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}

	if ctx == nil {
		WriteError(w, http.StatusNotFound, "service not found")
		return
	}

	story := buildWorkloadStory(ctx)
	WriteJSON(w, http.StatusOK, map[string]any{
		"service_name": serviceName,
		"story":        story,
	})
}

// fetchWorkloadContext queries Neo4j for workload context with a custom WHERE clause.
func (h *EntityHandler) fetchWorkloadContext(ctx context.Context, whereClause string, params map[string]any) (map[string]any, error) {
	cypher := fmt.Sprintf(`
		MATCH (w:Workload) WHERE %s
		OPTIONAL MATCH (r:Repository)-[:DEFINES]->(w)
		OPTIONAL MATCH (w)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[:RUNS_ON]->(p:Platform)
		RETURN w.id as id, w.name as name, w.kind as kind,
		       r.id as repo_id, r.name as repo_name,
		       collect(DISTINCT {instance_id: i.id, platform_name: p.name, platform_kind: p.kind, environment: i.environment}) as instances
	`, whereClause)

	row, err := h.Neo4j.RunSingle(ctx, cypher, params)
	if err != nil {
		return nil, err
	}

	if row == nil {
		return nil, nil
	}

	return map[string]any{
		"id":        StringVal(row, "id"),
		"name":      StringVal(row, "name"),
		"kind":      StringVal(row, "kind"),
		"repo_id":   StringVal(row, "repo_id"),
		"repo_name": StringVal(row, "repo_name"),
		"instances": extractInstances(row),
	}, nil
}

// extractRelationships converts the Neo4j relationships collection to typed structs.
func extractRelationships(row map[string]any) []map[string]any {
	return extractCollection(row, "relationships", func(m map[string]any) (map[string]any, bool) {
		if relType := StringVal(m, "type"); relType != "" {
			return map[string]any{
				"type":        relType,
				"target_name": StringVal(m, "target_name"),
				"target_id":   StringVal(m, "target_id"),
			}, true
		}
		return nil, false
	})
}

// extractInstances converts the Neo4j instances collection to typed structs.
func extractInstances(row map[string]any) []map[string]any {
	return extractCollection(row, "instances", func(m map[string]any) (map[string]any, bool) {
		if instID := StringVal(m, "instance_id"); instID != "" {
			return map[string]any{
				"instance_id":   instID,
				"platform_name": StringVal(m, "platform_name"),
				"platform_kind": StringVal(m, "platform_kind"),
				"environment":   StringVal(m, "environment"),
			}, true
		}
		return nil, false
	})
}

// extractCollection is a generic helper for extracting Neo4j collections.
func extractCollection(row map[string]any, key string, transform func(map[string]any) (map[string]any, bool)) []map[string]any {
	raw, ok := row[key]
	if !ok || raw == nil {
		return []map[string]any{}
	}
	items, ok := raw.([]any)
	if !ok {
		return []map[string]any{}
	}
	result := make([]map[string]any, 0, len(items))
	for _, item := range items {
		if m, ok := item.(map[string]any); ok {
			if transformed, valid := transform(m); valid {
				result = append(result, transformed)
			}
		}
	}
	return result
}

// buildWorkloadStory creates a narrative summary of a workload's deployment.
func buildWorkloadStory(ctx map[string]any) string {
	if ctx == nil {
		return ""
	}
	name, kind, repoName := safeStr(ctx, "name"), safeStr(ctx, "kind"), safeStr(ctx, "repo_name")
	story := "Workload " + name
	if kind != "" {
		story += " (kind: " + kind + ")"
	}
	if repoName != "" {
		story += " is defined in repository " + repoName + "."
	} else {
		story += " has no linked repository."
	}
	instances, ok := ctx["instances"].([]map[string]any)
	if !ok || len(instances) == 0 {
		return story + " No deployed instances found."
	}
	instCount := "1 instance"
	if len(instances) > 1 {
		instCount = fmt.Sprintf("%d instances", len(instances))
	}
	story += " It is deployed as " + instCount + ":"
	for _, inst := range instances {
		env, platform, platformKind := safeStr(inst, "environment"), safeStr(inst, "platform_name"), safeStr(inst, "platform_kind")
		story += " " + env + " on " + platform
		if platformKind != "" {
			story += " (" + platformKind + ")"
		}
		story += ";"
	}
	return story
}

// safeStr extracts a string from a map, filtering out empty and nil values.
func safeStr(m map[string]any, key string) string {
	v := fmt.Sprintf("%v", m[key])
	if v == "" || v == "<nil>" {
		return ""
	}
	return v
}
