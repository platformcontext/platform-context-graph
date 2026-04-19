package query

import (
	"context"
	"database/sql"
	"fmt"
	"net/http"
	"time"
)

const repositorySelectorWhereClause = "r.id = $repo_selector OR r.name = $repo_selector"

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
	repoSelector := PathParam(r, "repo_id")
	if repoSelector == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}
	ctx := r.Context()
	params := map[string]any{"repo_selector": repoSelector}

	baseCypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE %s
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		OPTIONAL MATCH (r)-[:DEFINES]->(w:Workload)
		OPTIONAL MATCH (r)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[:RUNS_ON]->(p:Platform)
		OPTIONAL MATCH (r)-[:DEPENDS_ON|USES_MODULE|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON]->(dep:Repository)
		RETURN %s,
		       count(DISTINCT f) as file_count,
		       count(DISTINCT w) as workload_count,
		       count(DISTINCT p) as platform_count,
		       count(DISTINCT dep) as dependency_count
	`, repositorySelectorWhereClause, RepoProjection("r"))

	baseRow, err := h.Neo4j.RunSingle(ctx, baseCypher, params)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if baseRow == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}
	repoID := StringVal(baseRow, "id")
	params = map[string]any{"repo_id": repoID}

	result := map[string]any{
		"repository":       RepoRefFromRow(baseRow),
		"file_count":       IntVal(baseRow, "file_count"),
		"workload_count":   IntVal(baseRow, "workload_count"),
		"platform_count":   IntVal(baseRow, "platform_count"),
		"dependency_count": IntVal(baseRow, "dependency_count"),
	}

	result["entry_points"] = queryRepoEntryPoints(ctx, h.Neo4j, params)
	result["infrastructure"] = queryRepoInfrastructure(ctx, h.Neo4j, h.Content, params)
	result["relationships"] = queryRepoDependencies(ctx, h.Neo4j, params)
	if relationshipOverview := buildRepositoryRelationshipOverview(result["relationships"].([]map[string]any)); relationshipOverview != nil {
		result["relationship_overview"] = relationshipOverview
	}
	result["consumers"] = queryRepoConsumers(ctx, h.Neo4j, params)
	if h.Content != nil {
		files, err := h.Content.ListRepoFiles(ctx, repoID, repositorySemanticEntityLimit)
		if err == nil {
			if files == nil {
				files = []FileContent{}
			}
			overview := buildRepositoryInfrastructureOverview(result["infrastructure"].([]map[string]any), files)
			deploymentOverview, _ := loadDeploymentArtifactOverview(
				ctx,
				h.Neo4j,
				h.Content,
				repoID,
				StringVal(baseRow, "name"),
				files,
				overview,
			)
			if deploymentOverview != nil {
				overview = deploymentOverview
			}
			if overview != nil {
				if deploymentArtifacts := mapValue(overview, "deployment_artifacts"); len(deploymentArtifacts) > 0 {
					result["deployment_artifacts"] = deploymentArtifacts
				}
				result["infrastructure_overview"] = overview
			}
		}
	}
	result["languages"] = queryRepoLanguageDistribution(ctx, h.Neo4j, params)

	WriteJSON(w, http.StatusOK, result)
}

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

func queryRepoInfrastructure(ctx context.Context, reader GraphReader, content *ContentReader, params map[string]any) []map[string]any {
	return queryRepoInfrastructureRows(ctx, reader, content, params)
}

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

func queryRepoDependencies(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (r:Repository {id: $repo_id})-[rel:DEPENDS_ON|USES_MODULE|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON]->(target:Repository)
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

func queryRepoConsumers(ctx context.Context, reader GraphReader, params map[string]any) []map[string]any {
	rows, err := reader.Run(ctx, `
		MATCH (consumer:Repository)-[rel:DEPENDS_ON|USES_MODULE|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON]->(r:Repository {id: $repo_id})
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

func (h *RepositoryHandler) getRepositoryStory(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	cypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE %s
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		WITH r, count(DISTINCT f) as file_count, collect(DISTINCT f.language) as languages
		OPTIONAL MATCH (r)-[:DEFINES]->(w:Workload)
		WITH r, file_count, languages, collect(DISTINCT w.name) as workload_names
		OPTIONAL MATCH (r)-[:DEFINES]->(:Workload)<-[:INSTANCE_OF]-(i:WorkloadInstance)-[:RUNS_ON]->(p:Platform)
		WITH r, file_count, languages, workload_names, collect(DISTINCT p.type) as platform_types
		OPTIONAL MATCH (r)-[:DEPENDS_ON|USES_MODULE|DEPLOYS_FROM|DISCOVERS_CONFIG_IN|PROVISIONS_DEPENDENCY_FOR|RUNS_ON]->(dep:Repository)
		RETURN %s,
		       file_count,
		       languages,
		       workload_names,
		       platform_types,
		       count(DISTINCT dep) as dependency_count
	`, repositorySelectorWhereClause, RepoProjection("r"))

	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_selector": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}
	repoID = StringVal(row, "id")

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
	var infrastructureOverview map[string]any
	narrativeFiles := []FileContent(nil)
	if h.Content != nil {
		files, err := h.Content.ListRepoFiles(r.Context(), repoID, repositorySemanticEntityLimit)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("list repository files failed: %v", err))
			return
		}
		if files == nil {
			files = []FileContent{}
		}
		infrastructure := queryRepoInfrastructure(r.Context(), h.Neo4j, h.Content, map[string]any{"repo_id": repoID})
		infrastructureOverview = buildRepositoryInfrastructureOverview(infrastructure, files)
		deploymentOverview, _ := loadDeploymentArtifactOverview(
			r.Context(),
			h.Neo4j,
			h.Content,
			repoID,
			repo.Name,
			files,
			infrastructureOverview,
		)
		if deploymentOverview != nil {
			infrastructureOverview = deploymentOverview
		}
		narrativeFiles, err = hydrateRepositoryNarrativeFiles(r.Context(), h.Content, repoID, files)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, fmt.Sprintf("hydrate repository narrative files failed: %v", err))
			return
		}
		relationships := queryRepoDependencies(r.Context(), h.Neo4j, map[string]any{"repo_id": repoID})
		if relationshipOverview := buildRepositoryRelationshipOverview(relationships); relationshipOverview != nil {
			if infrastructureOverview == nil {
				infrastructureOverview = map[string]any{}
			}
			infrastructureOverview["relationship_overview"] = relationshipOverview
		}
	}

	response := buildRepositoryStoryResponse(
		repo,
		fileCount,
		languages,
		workloadNames,
		platformTypes,
		dependencyCount,
		infrastructureOverview,
		semanticOverview,
	)
	enrichRepositoryStoryResponseWithEvidence(response, semanticOverview, narrativeFiles)

	WriteJSON(w, http.StatusOK, response)
}

// getRepositoryStats returns repository statistics including entity counts.
func (h *RepositoryHandler) getRepositoryStats(w http.ResponseWriter, r *http.Request) {
	repoID := PathParam(r, "repo_id")
	if repoID == "" {
		WriteError(w, http.StatusBadRequest, "repo_id is required")
		return
	}

	cypher := fmt.Sprintf(`
		MATCH (r:Repository) WHERE %s
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		WITH r, count(f) as file_count, collect(DISTINCT f.language) as languages
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f2:File)-[:CONTAINS]->(e)
		RETURN %s,
		       file_count,
		       languages,
		       count(DISTINCT e) as entity_count,
		       collect(DISTINCT labels(e)[0]) as entity_types
	`, repositorySelectorWhereClause, RepoProjection("r"))

	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_selector": repoID})
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
	cypher := fmt.Sprintf("MATCH (r:Repository) WHERE %s RETURN r.id as id", repositorySelectorWhereClause)
	row, err := h.Neo4j.RunSingle(r.Context(), cypher, map[string]any{"repo_selector": repoID})
	if err != nil {
		WriteError(w, http.StatusInternalServerError, fmt.Sprintf("query failed: %v", err))
		return
	}
	if row == nil {
		WriteError(w, http.StatusNotFound, "repository not found")
		return
	}
	repoID = StringVal(row, "id")

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
	graphStats, err := h.queryRepositoryGraphCoverageStats(ctx, repoID)
	if err != nil {
		return nil, fmt.Errorf("query graph coverage stats: %w", err)
	}

	coverage := map[string]any{
		"repo_id":                  repoID,
		"file_count":               0,
		"entity_count":             0,
		"languages":                []map[string]any{},
		"graph_available":          graphStats.Available,
		"server_content_available": h.Content != nil && h.Content.db != nil,
		"graph_gap_count":          0,
		"content_gap_count":        0,
		"completeness_state":       "unknown",
		"content_last_indexed_at":  "",
		"last_error":               "",
		"summary": map[string]any{
			"graph_file_count":     graphStats.FileCount,
			"graph_entity_count":   graphStats.EntityCount,
			"content_file_count":   0,
			"content_entity_count": 0,
		},
	}
	if h.Content == nil || h.Content.db == nil {
		coverage["completeness_state"] = completenessStateForCoverage(
			graphStats.Available,
			false,
			0,
			0,
		)
		coverage["last_error"] = "content store not available"
		return coverage, nil
	}

	// Query file count
	var fileCount int
	err = h.Content.db.QueryRowContext(ctx, `
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

	fileIndexedAt, err := queryMaxIndexedAt(ctx, h.Content.db, "content_files", repoID)
	if err != nil {
		return nil, fmt.Errorf("query content file indexed_at: %w", err)
	}
	entityIndexedAt, err := queryMaxIndexedAt(ctx, h.Content.db, "content_entities", repoID)
	if err != nil {
		return nil, fmt.Errorf("query content entity indexed_at: %w", err)
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

	graphGapCount, contentGapCount := computeCoverageGapCounts(
		graphStats.FileCount,
		graphStats.EntityCount,
		fileCount,
		entityCount,
	)
	coverage["file_count"] = fileCount
	coverage["entity_count"] = entityCount
	coverage["languages"] = languages
	coverage["graph_gap_count"] = graphGapCount
	coverage["content_gap_count"] = contentGapCount
	coverage["completeness_state"] = completenessStateForCoverage(
		graphStats.Available,
		true,
		graphGapCount,
		contentGapCount,
	)
	if latest := latestCoverageTimestamp(fileIndexedAt, entityIndexedAt); !latest.IsZero() {
		coverage["content_last_indexed_at"] = latest.Format(time.RFC3339Nano)
	}
	summary := mapValue(coverage, "summary")
	summary["content_file_count"] = fileCount
	summary["content_entity_count"] = entityCount
	summary["content_files_last_indexed_at"] = formatCoverageTimestamp(fileIndexedAt)
	summary["content_entities_last_indexed_at"] = formatCoverageTimestamp(entityIndexedAt)
	summary["graph_gap_count"] = graphGapCount
	summary["content_gap_count"] = contentGapCount
	summary["completeness_state"] = coverage["completeness_state"]
	coverage["summary"] = summary
	return coverage, nil
}

type repositoryGraphCoverageStats struct {
	FileCount   int
	EntityCount int
	Available   bool
}

func (h *RepositoryHandler) queryRepositoryGraphCoverageStats(
	ctx context.Context,
	repoID string,
) (repositoryGraphCoverageStats, error) {
	if h.Neo4j == nil || repoID == "" {
		return repositoryGraphCoverageStats{}, nil
	}

	row, err := h.Neo4j.RunSingle(ctx, `
		MATCH (r:Repository {id: $repo_id})
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(f:File)
		WITH r, count(DISTINCT f) as file_count
		OPTIONAL MATCH (r)-[:REPO_CONTAINS]->(:File)-[:CONTAINS]->(e)
		RETURN file_count, count(DISTINCT e) as entity_count
	`, map[string]any{"repo_id": repoID})
	if err != nil {
		return repositoryGraphCoverageStats{}, err
	}
	if row == nil {
		return repositoryGraphCoverageStats{}, nil
	}
	return repositoryGraphCoverageStats{
		FileCount:   IntVal(row, "file_count"),
		EntityCount: IntVal(row, "entity_count"),
		Available:   true,
	}, nil
}

func queryMaxIndexedAt(ctx context.Context, db *sql.DB, table string, repoID string) (time.Time, error) {
	var indexedAt sql.NullTime
	err := db.QueryRowContext(ctx, fmt.Sprintf(`
		SELECT max(indexed_at) as indexed_at
		FROM %s
		WHERE repo_id = $1
	`, table), repoID).Scan(&indexedAt)
	if err != nil {
		return time.Time{}, err
	}
	if !indexedAt.Valid {
		return time.Time{}, nil
	}
	return indexedAt.Time.UTC(), nil
}

func computeCoverageGapCounts(
	graphFileCount int,
	graphEntityCount int,
	contentFileCount int,
	contentEntityCount int,
) (int, int) {
	graphGapCount := maxInt(contentFileCount-graphFileCount, 0) + maxInt(contentEntityCount-graphEntityCount, 0)
	contentGapCount := maxInt(graphFileCount-contentFileCount, 0) + maxInt(graphEntityCount-contentEntityCount, 0)
	return graphGapCount, contentGapCount
}

func completenessStateForCoverage(
	graphAvailable bool,
	contentAvailable bool,
	graphGapCount int,
	contentGapCount int,
) string {
	switch {
	case !graphAvailable && !contentAvailable:
		return "unknown"
	case !graphAvailable:
		return "graph_unavailable"
	case !contentAvailable:
		return "content_unavailable"
	case graphGapCount == 0 && contentGapCount == 0:
		return "complete"
	case graphGapCount > 0 && contentGapCount > 0:
		return "graph_and_content_partial"
	case graphGapCount > 0:
		return "graph_partial"
	default:
		return "content_partial"
	}
}

func latestCoverageTimestamp(timestamps ...time.Time) time.Time {
	var latest time.Time
	for _, ts := range timestamps {
		if ts.IsZero() {
			continue
		}
		if latest.IsZero() || ts.After(latest) {
			latest = ts
		}
	}
	return latest
}

func formatCoverageTimestamp(ts time.Time) string {
	if ts.IsZero() {
		return ""
	}
	return ts.UTC().Format(time.RFC3339Nano)
}

func maxInt(left int, right int) int {
	if left > right {
		return left
	}
	return right
}
