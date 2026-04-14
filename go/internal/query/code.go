package query

import (
	"context"
	"fmt"
	"net/http"
)

// CodeHandler provides HTTP routes for code-level queries: search, relationships,
// dead code detection, and complexity metrics.
type CodeHandler struct {
	Neo4j   *Neo4jReader
	Content *ContentReader
}

// Mount registers all /api/v0/code/* routes on the given mux.
func (h *CodeHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/code/search", h.handleSearch)
	mux.HandleFunc("POST /api/v0/code/relationships", h.handleRelationships)
	mux.HandleFunc("POST /api/v0/code/dead-code", h.handleDeadCode)
	mux.HandleFunc("POST /api/v0/code/complexity", h.handleComplexity)
	mux.HandleFunc("POST /api/v0/code/call-chain", h.handleCallChain)

	// Language-specific queries.
	lq := &LanguageQueryHandler{Neo4j: h.Neo4j, Content: h.Content}
	lq.Mount(mux)
}

// handleSearch searches code entities by name pattern or content.
func (h *CodeHandler) handleSearch(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Query    string `json:"query"`
		RepoID   string `json:"repo_id"`
		Language string `json:"language"`
		Limit    int    `json:"limit"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Query == "" {
		WriteError(w, http.StatusBadRequest, "query is required")
		return
	}
	if req.RepoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}
	if req.Limit <= 0 {
		req.Limit = 50
	}

	ctx := r.Context()

	// Search graph entities by name pattern
	graphResults, err := h.searchGraphEntities(ctx, req.RepoID, req.Query, req.Language, req.Limit)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	// If graph search returns results, return them
	if len(graphResults) > 0 {
		WriteJSON(w, http.StatusOK, map[string]any{
			"source":  "graph",
			"query":   req.Query,
			"repo_id": req.RepoID,
			"results": graphResults,
		})
		return
	}

	// Fall back to content-based search if no graph results
	contentResults, err := h.searchEntityContent(ctx, req.RepoID, req.Query, req.Limit)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"source":  "content",
		"query":   req.Query,
		"repo_id": req.RepoID,
		"results": contentResults,
	})
}

// searchGraphEntities finds entities by name pattern in the Neo4j graph.
func (h *CodeHandler) searchGraphEntities(ctx context.Context, repoID, query, language string, limit int) ([]map[string]any, error) {
	cypher := `
		MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE r.id = $repo_id AND e.name CONTAINS $query
	`
	params := map[string]any{
		"repo_id": repoID,
		"query":   query,
		"limit":   limit,
	}

	if language != "" {
		cypher += " AND (e.language = $language OR f.language = $language)"
		params["language"] = language
	}

	cypher += `
		RETURN e.id as entity_id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line
		ORDER BY e.name
		LIMIT $limit
	`

	rows, err := h.Neo4j.Run(ctx, cypher, params)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		results = append(results, map[string]any{
			"entity_id":  StringVal(row, "entity_id"),
			"name":       StringVal(row, "name"),
			"labels":     StringSliceVal(row, "labels"),
			"file_path":  StringVal(row, "file_path"),
			"repo_id":    StringVal(row, "repo_id"),
			"repo_name":  StringVal(row, "repo_name"),
			"language":   StringVal(row, "language"),
			"start_line": IntVal(row, "start_line"),
			"end_line":   IntVal(row, "end_line"),
		})
	}

	return h.enrichGraphSearchResultsWithContentMetadata(ctx, results, repoID, query, limit)
}

// searchEntityContent searches entity source code in the content store.
func (h *CodeHandler) searchEntityContent(ctx context.Context, repoID, pattern string, limit int) ([]map[string]any, error) {
	entities, err := h.Content.SearchEntityContent(ctx, repoID, pattern, limit)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(entities))
	for _, e := range entities {
		results = append(results, map[string]any{
			"entity_id":    e.EntityID,
			"entity_name":  e.EntityName,
			"entity_type":  e.EntityType,
			"file_path":    e.RelativePath,
			"start_line":   e.StartLine,
			"end_line":     e.EndLine,
			"language":     e.Language,
			"source_cache": e.SourceCache,
			"metadata":     e.Metadata,
			"repo_id":      e.RepoID,
		})
	}

	return results, nil
}

// handleRelationships returns incoming and outgoing relationships for an entity.
func (h *CodeHandler) handleRelationships(w http.ResponseWriter, r *http.Request) {
	var req struct {
		EntityID string `json:"entity_id"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.EntityID == "" {
		WriteError(w, http.StatusBadRequest, "entity_id is required")
		return
	}

	ctx := r.Context()

	cypher := `
		MATCH (e) WHERE e.id = $entity_id
		OPTIONAL MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		OPTIONAL MATCH (e)-[r]->(target)
		OPTIONAL MATCH (source)-[r2]->(e)
		RETURN e.id as id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
		       collect(DISTINCT {direction: 'outgoing', type: type(r), target_name: target.name, target_id: target.id}) as outgoing,
		       collect(DISTINCT {direction: 'incoming', type: type(r2), source_name: source.name, source_id: source.id}) as incoming
	`

	var (
		row map[string]any
		err error
	)
	if h.Neo4j != nil {
		row, err = h.Neo4j.RunSingle(ctx, cypher, map[string]any{"entity_id": req.EntityID})
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}
	}
	if row == nil {
		response, fallbackErr := h.relationshipsFromContent(ctx, req.EntityID)
		if fallbackErr != nil {
			WriteError(w, http.StatusInternalServerError, fallbackErr.Error())
			return
		}
		if response == nil {
			WriteError(w, http.StatusNotFound, "entity not found")
			return
		}
		WriteJSON(w, http.StatusOK, response)
		return
	}

	// Filter out null relationships
	outgoing := filterNullRelationships(row["outgoing"])
	incoming := filterNullRelationships(row["incoming"])

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
		"outgoing":   outgoing,
		"incoming":   incoming,
	}
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

func (h *CodeHandler) relationshipsFromContent(ctx context.Context, entityID string) (map[string]any, error) {
	if h == nil || h.Content == nil || entityID == "" {
		return nil, nil
	}

	entity, err := h.Content.GetEntityContent(ctx, entityID)
	if err != nil || entity == nil {
		return nil, err
	}

	relationshipSet, err := buildContentRelationshipSet(ctx, h.Content, *entity)
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

// handleDeadCode finds entities with no incoming references.
func (h *CodeHandler) handleDeadCode(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RepoID string `json:"repo_id"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.RepoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	ctx := r.Context()

	cypher := `
		MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE r.id = $repo_id AND NOT ()-[:CALLS|IMPORTS|REFERENCES]->(e)
		RETURN e.id as entity_id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line
		ORDER BY f.relative_path, e.name
		LIMIT 100
	`

	rows, err := h.Neo4j.Run(ctx, cypher, map[string]any{"repo_id": req.RepoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		results = append(results, map[string]any{
			"entity_id":  StringVal(row, "entity_id"),
			"name":       StringVal(row, "name"),
			"labels":     StringSliceVal(row, "labels"),
			"file_path":  StringVal(row, "file_path"),
			"repo_id":    StringVal(row, "repo_id"),
			"repo_name":  StringVal(row, "repo_name"),
			"language":   StringVal(row, "language"),
			"start_line": IntVal(row, "start_line"),
			"end_line":   IntVal(row, "end_line"),
		})
	}
	results, err = h.enrichGraphSearchResultsWithContentMetadata(ctx, results, req.RepoID, "", 100)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"repo_id": req.RepoID,
		"results": results,
	})
}

// handleCallChain finds the transitive call chain between two functions by
// following CALLS_FUNCTION / CALLS edges up to a configurable depth.
func (h *CodeHandler) handleCallChain(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Start    string `json:"start"`
		End      string `json:"end"`
		MaxDepth int    `json:"max_depth"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Start == "" {
		WriteError(w, http.StatusBadRequest, "start is required")
		return
	}
	if req.End == "" {
		WriteError(w, http.StatusBadRequest, "end is required")
		return
	}
	if req.MaxDepth <= 0 {
		req.MaxDepth = 5
	}
	if req.MaxDepth > 10 {
		req.MaxDepth = 10
	}

	ctx := r.Context()

	cypher := `
		MATCH path = shortestPath(
			(start)-[:CALLS_FUNCTION|CALLS*1..` + fmt.Sprintf("%d", req.MaxDepth) + `]->(end)
		)
		WHERE start.name CONTAINS $start AND end.name CONTAINS $end
		UNWIND nodes(path) as n
		RETURN [node IN nodes(path) | {id: node.id, name: node.name, labels: labels(node)}] as chain,
		       length(path) as depth
		LIMIT 5
	`

	rows, err := h.Neo4j.Run(ctx, cypher, map[string]any{
		"start": req.Start,
		"end":   req.End,
	})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	chains := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		chains = append(chains, map[string]any{
			"chain": row["chain"],
			"depth": IntVal(row, "depth"),
		})
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"start":  req.Start,
		"end":    req.End,
		"chains": chains,
	})
}

// handleComplexity returns relationship-based complexity metrics for an entity.
func (h *CodeHandler) handleComplexity(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RepoID   string `json:"repo_id"`
		EntityID string `json:"entity_id"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.EntityID == "" {
		WriteError(w, http.StatusBadRequest, "entity_id is required")
		return
	}

	ctx := r.Context()

	cypher := `
		MATCH (e) WHERE e.id = $entity_id
		OPTIONAL MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		OPTIONAL MATCH (e)-[r]->()
		OPTIONAL MATCH ()-[r2]->(e)
		RETURN e.id as id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
		       count(DISTINCT r) as outgoing_count,
		       count(DISTINCT r2) as incoming_count,
		       count(DISTINCT r) + count(DISTINCT r2) as total_relationships
	`

	row, err := h.Neo4j.RunSingle(ctx, cypher, map[string]any{"entity_id": req.EntityID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "entity not found")
		return
	}

	response := map[string]any{
		"entity_id":           StringVal(row, "id"),
		"name":                StringVal(row, "name"),
		"labels":              StringSliceVal(row, "labels"),
		"file_path":           StringVal(row, "file_path"),
		"repo_id":             StringVal(row, "repo_id"),
		"repo_name":           StringVal(row, "repo_name"),
		"language":            StringVal(row, "language"),
		"start_line":          IntVal(row, "start_line"),
		"end_line":            IntVal(row, "end_line"),
		"outgoing_count":      IntVal(row, "outgoing_count"),
		"incoming_count":      IntVal(row, "incoming_count"),
		"total_relationships": IntVal(row, "total_relationships"),
	}
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
