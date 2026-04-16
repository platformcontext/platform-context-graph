package query

import (
	"context"
	"fmt"
	"net/http"
)

// RepositoryHandler exposes HTTP routes for repository queries.
type RepositoryHandler struct {
	Neo4j   GraphReader
	Content *ContentReader
}

// Mount registers all repository routes on the given mux.
func (h *RepositoryHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/v0/repositories", h.listRepositories)
	mux.HandleFunc("GET /api/v0/repositories/{repo_id}/context", h.getRepositoryContext)
	mux.HandleFunc("GET /api/v0/repositories/{repo_id}/story", h.getRepositoryStory)
	mux.HandleFunc("GET /api/v0/repositories/{repo_id}/stats", h.getRepositoryStats)
	mux.HandleFunc("GET /api/v0/repositories/{repo_id}/coverage", h.getRepositoryCoverage)
}

// listRepositories returns all indexed repositories.
func (h *RepositoryHandler) listRepositories(w http.ResponseWriter, r *http.Request) {
	cypher := fmt.Sprintf(`
		MATCH (r:Repository)
		RETURN %s, coalesce(r.is_dependency, false) as is_dependency
		ORDER BY r.name
	`, RepoProjection("r"))

	rows, err := h.Neo4j.Run(r.Context(), cypher, nil)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}

	repos := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		repo := map[string]any{
			"id":            StringVal(row, "id"),
			"name":          StringVal(row, "name"),
			"path":          StringVal(row, "path"),
			"local_path":    StringVal(row, "local_path"),
			"remote_url":    StringVal(row, "remote_url"),
			"repo_slug":     StringVal(row, "repo_slug"),
			"has_remote":    BoolVal(row, "has_remote"),
			"is_dependency": BoolVal(row, "is_dependency"),
		}
		repos = append(repos, repo)
	}

	WriteJSON(w, http.StatusOK, map[string]any{
		"repositories": repos,
		"count":        len(repos),
	})
}

// getRepositoryContext returns repository metadata with graph statistics and
// enriched context including entry points, infrastructure entities, language
// distribution, cross-repo relationships, and consumer repositories.
func (h *RepositoryHandler) getRepositoryContext(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}
	ctx := r.Context()
	params := map[string]any{"repo_id": repoID}

	// Base query: repo metadata + aggregate counts.
	baseCypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE r.id = $repo_id
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		OPTIONAL MATCH (r)-[:DEFINES]->(w:Workload)
		OPTIONAL MATCH (r)-[:RUNS_ON]->(p:Platform)
		OPTIONAL MATCH (r)-[:DEPENDS_ON]->(dep:Repository)
		RETURN %s,
		       count(DISTINCT f) as file_count,
		       count(DISTINCT w) as workload_count,
		       count(DISTINCT p) as platform_count,
		       count(DISTINCT dep) as dependency_count
	`, RepoProjection("r"))

	baseRow, err := h.Neo4j.RunSingle(ctx, baseCypher, params)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if baseRow == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}

	result := map[string]any{
		"repository":       RepoRefFromRow(baseRow),
		"file_count":       IntVal(baseRow, "file_count"),
		"workload_count":   IntVal(baseRow, "workload_count"),
		"platform_count":   IntVal(baseRow, "platform_count"),
		"dependency_count": IntVal(baseRow, "dependency_count"),
	}

	// Enrichment queries run after the base query succeeds. Each is a focused
	// query that populates one section of the response. Errors in enrichment
	// queries are non-fatal — the base response is still returned.
	result["entry_points"] = queryRepoEntryPoints(ctx, h.Neo4j, params)
	result["infrastructure"] = queryRepoInfrastructure(ctx, h.Neo4j, params)
	result["languages"] = queryRepoLanguageDistribution(ctx, h.Neo4j, params)
	result["relationships"] = queryRepoDependencies(ctx, h.Neo4j, params)
	result["consumers"] = queryRepoConsumers(ctx, h.Neo4j, params)

	WriteJSON(w, http.StatusOK, result)
}

// queryRepoEntryPoints returns main functions, handlers, and app factories for
// a repository. Shared by RepositoryHandler and EntityHandler workload enrichment.
func queryRepoEntryPoints(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(fn:Function)
		WHERE fn.name IN ['main', 'handler', 'app', 'create_app', 'lambda_handler',
		                   'Main', 'Handler', 'App', 'CreateApp', 'LambdaHandler']
		RETURN fn.name AS name, f.relative_path AS relative_path, fn.language AS language
		ORDER BY fn.name
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result = append(result, map[string]any{
			"name":          StringVal(row, "name"),
			"relative_path": StringVal(row, "relative_path"),
			"language":      StringVal(row, "language"),
		})
	}
	return result
}

// queryRepoInfrastructure returns K8s, Terraform, and ArgoCD entities for a
// repository. Shared by RepositoryHandler and EntityHandler workload enrichment.
func queryRepoInfrastructure(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)-[:CONTAINS]->(infra)
		WHERE infra:K8sResource OR infra:TerraformResource OR infra:ArgoCDApplication
		      OR infra:HelmChart OR infra:CrossplaneXRD
		RETURN labels(infra)[0] AS type, infra.name AS name,
		       infra.kind AS kind, f.relative_path AS file_path
		ORDER BY type, name
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		entry := map[string]any{
			"type":      StringVal(row, "type"),
			"name":      StringVal(row, "name"),
			"file_path": StringVal(row, "file_path"),
		}
		if kind := StringVal(row, "kind"); kind != "" {
			entry["kind"] = kind
		}
		result = append(result, entry)
	}
	return result
}

// queryRepoLanguageDistribution returns file counts grouped by language for a
// repository.
func queryRepoLanguageDistribution(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[:REPO_CONTAINS]->(f:File)
		WHERE f.language IS NOT NULL
		RETURN f.language AS language, count(f) AS file_count
		ORDER BY file_count DESC
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result = append(result, map[string]any{
			"language":   StringVal(row, "language"),
			"file_count": IntVal(row, "file_count"),
		})
	}
	return result
}

// queryRepoDependencies returns outgoing cross-repo dependency edges for a
// repository. Shared by RepositoryHandler and EntityHandler workload enrichment.
func queryRepoDependencies(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[rel:DEPENDS_ON|DEPLOYS_FROM|DISCOVERS_CONFIG_IN]->(target:Repository)
		RETURN type(rel) AS type, target.name AS target_name,
		       target.id AS target_id, rel.evidence_type AS evidence_type
		ORDER BY type, target_name
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		entry := map[string]any{
			"type":        StringVal(row, "type"),
			"target_name": StringVal(row, "target_name"),
			"target_id":   StringVal(row, "target_id"),
		}
		if evidenceType := StringVal(row, "evidence_type"); evidenceType != "" {
			entry["evidence_type"] = evidenceType
		}
		result = append(result, entry)
	}
	return result
}

// queryRepoConsumers returns repos that depend on a given repository.
func queryRepoConsumers(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (consumer:Repository)-[:DEPENDS_ON]->(r:Repository {id: $repo_id})
		RETURN consumer.name AS consumer_name, consumer.id AS consumer_id
		ORDER BY consumer_name
	`, params)
	if err != nil || len(rows) == 0 {
		return make([]map[string]any, 0)
	}

	result := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result = append(result, map[string]any{
			"name": StringVal(row, "consumer_name"),
			"id":   StringVal(row, "consumer_id"),
		})
	}
	return result
}

// getRepositoryStory returns a narrative summary for the repository.
func (h *RepositoryHandler) getRepositoryStory(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	cypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE r.id = $repo_id
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		WITH r, count(DISTINCT f) as file_count, collect(DISTINCT f.language) as languages
		OPTIONAL MATCH (r)-[:DEFINES]->(w:Workload)
		WITH r, file_count, languages, collect(DISTINCT w.name) as workload_names
		OPTIONAL MATCH (r)-[:RUNS_ON]->(p:Platform)
		WITH r, file_count, languages, workload_names, collect(DISTINCT p.type) as platform_types
		OPTIONAL MATCH (r)-[:DEPENDS_ON]->(dep:Repository)
		RETURN %s,
		       file_count,
		       languages,
		       workload_names,
		       platform_types,
		       count(DISTINCT dep) as dependency_count
	`, RepoProjection("r"))

	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_id": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}

	repo := RepoRefFromRow(row)
	fileCount := IntVal(row, "file_count")
	languages := StringSliceVal(row, "languages")
	workloadNames := StringSliceVal(row, "workload_names")
	platformTypes := StringSliceVal(row, "platform_types")
	dependencyCount := IntVal(row, "dependency_count")
	semanticOverview, err := loadRepositorySemanticOverview(r.Context(), h.Content, repoID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("semantic overview failed: %v", err))
		return
	}

	WriteJSON(w, http.StatusOK, buildRepositoryStoryResponse(
		repo,
		fileCount,
		languages,
		workloadNames,
		platformTypes,
		dependencyCount,
		semanticOverview,
	))
}

// getRepositoryStats returns repository statistics including entity counts.
func (h *RepositoryHandler) getRepositoryStats(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	cypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE r.id = $repo_id
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		WITH r, count(f) as file_count, collect(DISTINCT f.language) as languages
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f2:File)-[:CONTAINS]->(e)
		RETURN %s,
		       file_count,
		       languages,
		       count(DISTINCT e) as entity_count,
		       collect(DISTINCT labels(e)[0]) as entity_types
	`, RepoProjection("r"))

	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_id": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}

	stats := map[string]any{
		"repository":   RepoRefFromRow(row),
		"file_count":   IntVal(row, "file_count"),
		"languages":    StringSliceVal(row, "languages"),
		"entity_count": IntVal(row, "entity_count"),
		"entity_types": StringSliceVal(row, "entity_types"),
	}

	WriteJSON(w, http.StatusOK, stats)
}

// getRepositoryCoverage returns content store coverage for the repository.
func (h *RepositoryHandler) getRepositoryCoverage(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	// Check if repository exists
	cypher := "MATCH (r:Repository) WHERE r.id = $repo_id RETURN r.id as id"
	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_id": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}

	// Get content store coverage
	coverage, err := h.queryContentStoreCoverage(r.Context(), repoID)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("coverage query failed: %v", err))
		return
	}

	WriteJSON(w, http.StatusOK, coverage)
}

// queryContentStoreCoverage queries the Postgres content store for repository coverage.
func (h *RepositoryHandler) queryContentStoreCoverage(ctx context.Context, repoID string) (map[string]any, error) {
	if h.Content == nil || h.Content.db == nil {
		return map[string]any{
			"repo_id":      repoID,
			"file_count":   0,
			"entity_count": 0,
			"error":        "content store not available",
		}, nil
	}

	// Query file count
	var fileCount int
	err := h.Content.db.QueryRowContext(ctx, `
		SELECT count(*) FROM content_files WHERE repo_id = $1
	`, repoID).Scan(&fileCount)
	if err != nil {
		return nil, fmt.Errorf("query file count: %w", err)
	}

	// Query entity count
	var entityCount int
	err = h.Content.db.QueryRowContext(ctx, `
		SELECT count(*) FROM content_entities WHERE repo_id = $1
	`, repoID).Scan(&entityCount)
	if err != nil {
		return nil, fmt.Errorf("query entity count: %w", err)
	}

	// Query languages distribution
	rows, err := h.Content.db.QueryContext(ctx, `
		SELECT coalesce(language, 'unknown') as language, count(*) as file_count
		FROM content_files
		WHERE repo_id = $1
		GROUP BY language
		ORDER BY file_count DESC
	`, repoID)
	if err != nil {
		return nil, fmt.Errorf("query language distribution: %w", err)
	}
	defer func() { _ = rows.Close() }()

	languages := make([]map[string]any, 0)
	for rows.Next() {
		var lang string
		var count int
		if err := rows.Scan(&lang, &count); err != nil {
			return nil, fmt.Errorf("scan language row: %w", err)
		}
		languages = append(languages, map[string]any{
			"language":   lang,
			"file_count": count,
		})
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate language rows: %w", err)
	}

	return map[string]any{
		"repo_id":      repoID,
		"file_count":   fileCount,
		"entity_count": entityCount,
		"languages":    languages,
	}, nil
}
