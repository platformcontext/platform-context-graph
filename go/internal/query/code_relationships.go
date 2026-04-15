package query

import (
	"context"
	"errors"
	"net/http"
	"strings"
)

type relationshipsRequest struct {
	EntityID         string `json:"entity_id"`
	Name             string `json:"name"`
	Direction        string `json:"direction"`
	RelationshipType string `json:"relationship_type"`
}

// handleRelationships returns incoming and outgoing relationships for an entity.
func (h *CodeHandler) handleRelationships(w http.ResponseWriter, r *http.Request) {
	var req relationshipsRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	if req.EntityID == "" && strings.TrimSpace(req.Name) == "" {
		WriteError(w, http.StatusBadRequest, "entity_id or name is required")
		return
	}

	direction, err := normalizeRelationshipDirection(req.Direction)
	if err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	relationshipType := strings.ToUpper(strings.TrimSpace(req.RelationshipType))
	ctx := r.Context()

	row, err := h.relationshipsGraphRow(ctx, req.EntityID, req.Name)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if row == nil {
		response, fallbackErr := h.relationshipsFromContent(ctx, req.EntityID, req.Name)
		if fallbackErr != nil {
			WriteError(w, http.StatusInternalServerError, fallbackErr.Error())
			return
		}
		if response == nil {
			WriteError(w, http.StatusNotFound, "entity not found")
			return
		}
		WriteJSON(w, http.StatusOK, filterRelationshipResponse(response, direction, relationshipType))
		return
	}

	response := map[string]any{
		"entity_id":  StringVal(row, "id"),
		"name":       StringVal(row, "name"),
		"labels":     StringSliceVal(row, "labels"),
		"file_path":  StringVal(row, "file_path"),
		"repo_id":    StringVal(row, "repo_id"),
		"repo_name":  StringVal(row, "repo_name"),
		"language":   StringVal(row, "language"),
		"start_line": IntVal(row, "start_line"),
		"end_line":   IntVal(row, "end_line"),
		"outgoing":   filterNullRelationships(row["outgoing"]),
		"incoming":   filterNullRelationships(row["incoming"]),
	}
	normalizeGraphRelationships(response)
	response = filterRelationshipResponse(response, direction, relationshipType)
	enriched, err := h.enrichGraphSearchResultsWithContentMetadata(
		ctx,
		[]map[string]any{response},
		StringVal(row, "repo_id"),
		StringVal(row, "name"),
		1,
	)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	WriteJSON(w, http.StatusOK, enriched[0])
}

func (h *CodeHandler) relationshipsGraphRow(
	ctx context.Context,
	entityID string,
	name string,
) (map[string]any, error) {
	if h == nil || h.Neo4j == nil {
		return nil, nil
	}

	if strings.TrimSpace(entityID) != "" {
		return h.Neo4j.RunSingle(ctx, relationshipGraphRowCypher("e.id = $entity_id"), map[string]any{
			"entity_id": entityID,
		})
	}
	if strings.TrimSpace(name) == "" {
		return nil, nil
	}

	rows, err := h.Neo4j.Run(ctx, relationshipGraphRowCypher("e.name = $name"), map[string]any{
		"name": name,
	})
	if err != nil {
		return nil, err
	}
	if len(rows) != 1 {
		return nil, nil
	}
	return rows[0], nil
}

func relationshipGraphRowCypher(predicate string) string {
	return `
		MATCH (e) WHERE ` + predicate + `
		OPTIONAL MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		OPTIONAL MATCH (e)-[r]->(target)
		OPTIONAL MATCH (source)-[r2]->(e)
		RETURN e.id as id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
		       collect(DISTINCT {direction: 'outgoing', type: type(r), call_kind: r.call_kind, target_name: target.name, target_id: target.id}) as outgoing,
		       collect(DISTINCT {direction: 'incoming', type: type(r2), call_kind: r2.call_kind, source_name: source.name, source_id: source.id}) as incoming
		LIMIT 2
	`
}

func normalizeGraphRelationships(response map[string]any) {
	response["outgoing"] = normalizeGraphRelationshipSlice(mapRelationships(response["outgoing"]))
	response["incoming"] = normalizeGraphRelationshipSlice(mapRelationships(response["incoming"]))
}

func normalizeGraphRelationshipSlice(relationships []map[string]any) []map[string]any {
	if len(relationships) == 0 {
		return relationships
	}
	normalized := make([]map[string]any, 0, len(relationships))
	for _, relationship := range relationships {
		item := make(map[string]any, len(relationship)+1)
		for key, value := range relationship {
			item[key] = value
		}
		if StringVal(item, "type") == "CALLS" && StringVal(item, "call_kind") == "jsx_component" {
			item["type"] = "REFERENCES"
			item["reason"] = "jsx_component_call_kind"
		}
		normalized = append(normalized, item)
	}
	return normalized
}

func (h *CodeHandler) relationshipsFromContent(
	ctx context.Context,
	entityID string,
	name string,
) (map[string]any, error) {
	if h == nil || h.Content == nil {
		return nil, nil
	}

	entity, err := h.resolveRelationshipEntity(ctx, entityID, name)
	if err != nil || entity == nil {
		return nil, err
	}

	return h.relationshipsFromEntity(ctx, *entity)
}

func (h *CodeHandler) resolveRelationshipEntity(
	ctx context.Context,
	entityID string,
	name string,
) (*EntityContent, error) {
	if strings.TrimSpace(entityID) != "" {
		return h.Content.GetEntityContent(ctx, entityID)
	}
	if strings.TrimSpace(name) == "" {
		return nil, nil
	}

	matches, err := h.Content.SearchEntitiesByNameAnyRepo(ctx, "", name, 2)
	if err != nil {
		return nil, err
	}
	if len(matches) != 1 {
		return nil, nil
	}
	return &matches[0], nil
}

func (h *CodeHandler) relationshipsFromEntity(
	ctx context.Context,
	entity EntityContent,
) (map[string]any, error) {
	relationshipSet, err := buildContentRelationshipSet(ctx, h.Content, entity)
	if err != nil {
		return nil, err
	}

	return map[string]any{
		"entity_id":  entity.EntityID,
		"name":       entity.EntityName,
		"labels":     []string{entity.EntityType},
		"file_path":  entity.RelativePath,
		"repo_id":    entity.RepoID,
		"language":   entity.Language,
		"start_line": entity.StartLine,
		"end_line":   entity.EndLine,
		"metadata":   entity.Metadata,
		"outgoing":   relationshipSet.outgoing,
		"incoming":   relationshipSet.incoming,
	}, nil
}

func normalizeRelationshipDirection(direction string) (string, error) {
	switch normalized := strings.ToLower(strings.TrimSpace(direction)); normalized {
	case "", "incoming", "outgoing":
		return normalized, nil
	default:
		return "", errors.New("direction must be incoming or outgoing")
	}
}

func filterRelationshipResponse(
	response map[string]any,
	direction string,
	relationshipType string,
) map[string]any {
	filtered := make(map[string]any, len(response))
	for key, value := range response {
		filtered[key] = value
	}

	outgoing := filterRelationships(mapRelationships(response["outgoing"]), relationshipType)
	incoming := filterRelationships(mapRelationships(response["incoming"]), relationshipType)
	if direction == "incoming" {
		outgoing = []map[string]any{}
	}
	if direction == "outgoing" {
		incoming = []map[string]any{}
	}

	filtered["outgoing"] = outgoing
	filtered["incoming"] = incoming
	return filtered
}

func filterRelationships(relationships []map[string]any, relationshipType string) []map[string]any {
	if len(relationships) == 0 {
		return []map[string]any{}
	}
	if relationshipType == "" {
		return relationships
	}

	filtered := make([]map[string]any, 0, len(relationships))
	for _, relationship := range relationships {
		if strings.EqualFold(StringVal(relationship, "type"), relationshipType) {
			filtered = append(filtered, relationship)
		}
	}
	return filtered
}

func mapRelationships(value any) []map[string]any {
	relationships, ok := value.([]map[string]any)
	if ok {
		return relationships
	}
	return filterNullRelationships(value)
}
