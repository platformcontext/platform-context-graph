package query

import (
	"context"
	"net/http"
	"slices"
	"strings"
)

// GraphReader is the read-only graph surface shared by query handlers.
type GraphReader interface {
	Run(context.Context, string, map[string]any) ([]map[string]any, error)
	RunSingle(context.Context, string, map[string]any) (map[string]any, error)
}

// CodeHandler provides HTTP routes for code-level queries: search, relationships,
// dead code detection, and complexity metrics.
type CodeHandler struct {
	Neo4j   GraphReader
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
	contentResults, err := h.searchEntityContent(ctx, req.RepoID, req.Query, req.Language, req.Limit)
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
func (h *CodeHandler) searchEntityContent(ctx context.Context, repoID, pattern, language string, limit int) ([]map[string]any, error) {
	nameMatches, err := h.Content.SearchEntitiesByName(ctx, repoID, "", pattern, limit)
	if err != nil {
		return nil, err
	}
	sourceMatches, err := h.Content.SearchEntityContent(ctx, repoID, pattern, limit)
	if err != nil {
		return nil, err
	}

	allowedLanguages := make(map[string]struct{})
	if strings.TrimSpace(language) != "" {
		for _, variant := range normalizedLanguageVariants(language) {
			allowedLanguages[variant] = struct{}{}
		}
	}

	results := make([]map[string]any, 0, len(nameMatches)+len(sourceMatches))
	seen := make(map[string]struct{}, len(nameMatches)+len(sourceMatches))
	appendResult := func(entity EntityContent) {
		if entity.EntityID == "" {
			return
		}
		if len(allowedLanguages) > 0 {
			if _, ok := allowedLanguages[entity.Language]; !ok {
				return
			}
		}
		if _, ok := seen[entity.EntityID]; ok {
			return
		}
		seen[entity.EntityID] = struct{}{}
		results = append(results, map[string]any{
			"entity_id":    entity.EntityID,
			"entity_name":  entity.EntityName,
			"entity_type":  entity.EntityType,
			"file_path":    entity.RelativePath,
			"start_line":   entity.StartLine,
			"end_line":     entity.EndLine,
			"language":     entity.Language,
			"source_cache": entity.SourceCache,
			"metadata":     entity.Metadata,
			"repo_id":      entity.RepoID,
		})
		attachSemanticSummary(results[len(results)-1])
	}

	for _, entity := range nameMatches {
		appendResult(entity)
	}
	for _, entity := range sourceMatches {
		appendResult(entity)
	}

	return results, nil
}

// handleDeadCode finds entities with no incoming references.
func (h *CodeHandler) handleDeadCode(w http.ResponseWriter, r *http.Request) {
	var req struct {
		RepoID               string   `json:"repo_id"`
		ExcludeDecoratedWith []string `json:"exclude_decorated_with"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	ctx := r.Context()

	cypher := `
		MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE NOT ()-[:CALLS|IMPORTS|REFERENCES]->(e)
	`
	params := map[string]any{}
	if req.RepoID != "" {
		cypher += ` AND r.id = $repo_id`
		params["repo_id"] = req.RepoID
	}
	cypher += `
		RETURN e.id as entity_id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line
		ORDER BY f.relative_path, e.name
		LIMIT 100
	`

	rows, err := h.Neo4j.Run(ctx, cypher, params)
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
	results, err = h.enrichGraphResultsWithContentMetadataByEntityID(ctx, results)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	results = filterResultsByDecoratorExclusions(results, req.ExcludeDecoratedWith)

	WriteJSON(w, http.StatusOK, map[string]any{
		"repo_id": req.RepoID,
		"results": results,
	})
}

func filterResultsByDecoratorExclusions(results []map[string]any, excluded []string) []map[string]any {
	if len(results) == 0 || len(excluded) == 0 {
		return results
	}

	normalizedExcluded := make([]string, 0, len(excluded))
	for _, decorator := range excluded {
		if normalized := normalizeDecoratorName(decorator); normalized != "" {
			normalizedExcluded = append(normalizedExcluded, normalized)
		}
	}
	if len(normalizedExcluded) == 0 {
		return results
	}

	filtered := make([]map[string]any, 0, len(results))
	for _, result := range results {
		metadata, ok := result["metadata"].(map[string]any)
		if !ok {
			filtered = append(filtered, result)
			continue
		}
		if !resultMatchesDecoratorExclusion(metadata, normalizedExcluded) {
			filtered = append(filtered, result)
		}
	}

	return filtered
}

func resultMatchesDecoratorExclusion(metadata map[string]any, excluded []string) bool {
	rawDecorators, ok := metadata["decorators"].([]any)
	if !ok {
		return false
	}

	for _, raw := range rawDecorators {
		decorator, ok := raw.(string)
		if !ok {
			continue
		}
		if slices.Contains(excluded, normalizeDecoratorName(decorator)) {
			return true
		}
	}

	return false
}

func normalizeDecoratorName(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	return strings.TrimPrefix(trimmed, "@")
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
