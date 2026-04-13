package query

import (
	"context"
	"fmt"
	"net/http"
	"strings"
)

// RepositoryHandler exposes HTTP routes for repository queries.
type RepositoryHandler struct {
	Neo4j   *Neo4jReader
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

// getRepositoryContext returns repository metadata with graph statistics.
func (h *RepositoryHandler) getRepositoryContext(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	cypher := fmt.Sprintf(`
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

	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_id": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}

	context := map[string]any{
		"repository":       RepoRefFromRow(row),
		"file_count":       IntVal(row, "file_count"),
		"workload_count":   IntVal(row, "workload_count"),
		"platform_count":   IntVal(row, "platform_count"),
		"dependency_count": IntVal(row, "dependency_count"),
	}

	WriteJSON(w, http.StatusOK, context)
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
		RETURN %s,
		       file_count,
		       languages,
		       workload_names,
		       collect(DISTINCT p.type) as platform_types
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

	story := h.buildRepositoryStory(repo, fileCount, languages, workloadNames, platformTypes)

	WriteJSON(w, http.StatusOK, map[string]any{
		"repository": repo,
		"story":      story,
	})
}

// buildRepositoryStory constructs a narrative summary.
func (h *RepositoryHandler) buildRepositoryStory(
	repo RepoRef,
	fileCount int,
	languages []string,
	workloads []string,
	platforms []string,
) string {
	var parts []string

	parts = append(parts, fmt.Sprintf("Repository %s contains %d indexed files.", repo.Name, fileCount))

	if len(languages) > 0 {
		filteredLangs := make([]string, 0, len(languages))
		for _, lang := range languages {
			if lang != "" {
				filteredLangs = append(filteredLangs, lang)
			}
		}
		if len(filteredLangs) > 0 {
			parts = append(parts, fmt.Sprintf("Languages: %s.", strings.Join(filteredLangs, ", ")))
		}
	}

	if len(workloads) > 0 {
		parts = append(parts, fmt.Sprintf("Defines %d workload(s): %s.", len(workloads), strings.Join(workloads, ", ")))
	}

	if len(platforms) > 0 {
		filteredPlatforms := make([]string, 0, len(platforms))
		for _, p := range platforms {
			if p != "" {
				filteredPlatforms = append(filteredPlatforms, p)
			}
		}
		if len(filteredPlatforms) > 0 {
			parts = append(parts, fmt.Sprintf("Runs on platform(s): %s.", strings.Join(filteredPlatforms, ", ")))
		}
	}

	if repo.HasRemote && repo.RemoteURL != "" {
		parts = append(parts, fmt.Sprintf("Remote URL: %s.", repo.RemoteURL))
	}

	return strings.Join(parts, " ")
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
