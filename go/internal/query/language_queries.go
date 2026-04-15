package query

import (
	"context"
	"fmt"
	"net/http"
	"strings"
)

// LanguageQueryHandler provides language-specific entity queries against the
// graph and content store. Graph-backed entity types use Neo4j. Content-only
// entity types use the Postgres content store.
type LanguageQueryHandler struct {
	Neo4j   GraphReader
	Content *ContentReader
}

// graphBackedEntityTypes maps the user-facing entity type name to the Neo4j
// node label used in Cypher queries.
var graphBackedEntityTypes = map[string]string{
	"repository": "Repository",
	"directory":  "Directory",
	"file":       "File",
	"module":     "Module",
	"function":   "Function",
	"class":      "Class",
	"struct":     "Struct",
	"enum":       "Enum",
	"union":      "Union",
	"macro":      "Macro",
	"variable":   "Variable",
}

// contentBackedEntityTypes maps user-facing entity types to content-entity
// labels that are already materialized in Postgres but not yet first-class in
// the graph query surface.
var contentBackedEntityTypes = map[string]string{
	"type_alias":              "TypeAlias",
	"type_annotation":         "TypeAnnotation",
	"typedef":                 "Typedef",
	"annotation":              "Annotation",
	"protocol":                "Protocol",
	"impl_block":              "ImplBlock",
	"component":               "Component",
	"terragrunt_dependency":   "TerragruntDependency",
	"terragrunt_local":        "TerragruntLocal",
	"terragrunt_input":        "TerragruntInput",
	"guard":                   "guard",
	"protocol_implementation": "ProtocolImplementation",
	"module_attribute":        "module_attribute",
}

var graphFirstContentBackedEntityTypes = map[string]string{"annotation": "Annotation", "impl_block": "ImplBlock"}

// Mount registers the language query endpoint on the given mux.
func (h *LanguageQueryHandler) Mount(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/v0/code/language-query", h.handleLanguageQuery)
}

// handleLanguageQuery dispatches a language-specific entity query.
func (h *LanguageQueryHandler) handleLanguageQuery(w http.ResponseWriter, r *http.Request) {
	var req struct {
		Language   string `json:"language"`
		EntityType string `json:"entity_type"`
		Query      string `json:"query"`
		RepoID     string `json:"repo_id"`
		Limit      int    `json:"limit"`
	}
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}

	if req.Language == "" {
		WriteError(w, http.StatusBadRequest, "language is required")
		return
	}
	if req.EntityType == "" {
		WriteError(w, http.StatusBadRequest, "entity_type is required")
		return
	}

	req.Language = canonicalLanguage(req.Language)
	req.EntityType = strings.ToLower(strings.TrimSpace(req.EntityType))

	if !supportedLanguages[req.Language] {
		WriteError(w, http.StatusBadRequest, fmt.Sprintf(
			"unsupported language %q; supported: %s",
			req.Language, joinKeys(supportedLanguages),
		))
		return
	}

	if req.Limit <= 0 {
		req.Limit = 50
	}

	if label, ok := graphBackedEntityTypes[req.EntityType]; ok {
		results, err := h.queryByLanguage(r.Context(), req.Language, label, req.Query, req.RepoID, req.Limit)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}

		WriteJSON(w, http.StatusOK, map[string]any{
			"language":    req.Language,
			"entity_type": req.EntityType,
			"query":       req.Query,
			"results":     results,
		})
		return
	}

	if label, ok := graphFirstContentBackedEntityTypes[req.EntityType]; ok {
		results, err := h.queryGraphFirstContentByLanguage(
			r.Context(),
			req.Language,
			label,
			req.Query,
			req.RepoID,
			req.Limit,
		)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}

		WriteJSON(w, http.StatusOK, map[string]any{
			"language":    req.Language,
			"entity_type": req.EntityType,
			"query":       req.Query,
			"results":     results,
		})
		return
	}

	if label, ok := contentBackedEntityTypes[req.EntityType]; ok {
		results, err := h.queryContentByLanguage(r.Context(), req.Language, label, req.Query, req.RepoID, req.Limit)
		if err != nil {
			WriteError(w, http.StatusInternalServerError, err.Error())
			return
		}

		WriteJSON(w, http.StatusOK, map[string]any{
			"language":    req.Language,
			"entity_type": req.EntityType,
			"query":       req.Query,
			"results":     results,
		})
		return
	}

	WriteError(w, http.StatusBadRequest, fmt.Sprintf(
		"unsupported entity_type %q; supported: %s",
		req.EntityType, joinKeys(allSupportedEntityTypes()),
	))
}

func (h *LanguageQueryHandler) queryContentByLanguage(
	ctx context.Context,
	language, entityType, query, repoID string,
	limit int,
) ([]map[string]any, error) {
	if h.Content == nil {
		return nil, fmt.Errorf("content reader is required for %s queries", entityType)
	}

	rows, err := h.Content.SearchEntitiesByLanguageAndType(ctx, repoID, language, entityType, query, limit)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result := map[string]any{
			"entity_id":  row.EntityID,
			"name":       row.EntityName,
			"labels":     []string{row.EntityType},
			"file_path":  row.RelativePath,
			"repo_id":    row.RepoID,
			"language":   row.Language,
			"start_line": row.StartLine,
			"end_line":   row.EndLine,
			"metadata":   row.Metadata,
		}
		attachSemanticSummary(result)
		results = append(results, result)
	}

	return results, nil
}

func allSupportedEntityTypes() map[string]string {
	merged := make(map[string]string, len(graphBackedEntityTypes)+len(contentBackedEntityTypes))
	for key, value := range graphBackedEntityTypes {
		merged[key] = value
	}
	for key, value := range contentBackedEntityTypes {
		merged[key] = value
	}
	return merged
}

// queryByLanguage builds and executes a language-specific Cypher query.
func (h *LanguageQueryHandler) queryByLanguage(
	ctx context.Context,
	language, label, query, repoID string,
	limit int,
) ([]map[string]any, error) {
	cypher, params := buildLanguageCypher(language, label, query, repoID, limit)

	rows, err := h.Neo4j.Run(ctx, cypher, params)
	if err != nil {
		return nil, err
	}

	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		results = append(results, buildLanguageResult(row, label))
	}
	return h.enrichLanguageResultsWithContentMetadata(
		ctx,
		results,
		language,
		label,
		query,
		repoID,
		limit,
	)
}

func (h *LanguageQueryHandler) queryGraphFirstContentByLanguage(
	ctx context.Context,
	language, label, query, repoID string,
	limit int,
) ([]map[string]any, error) {
	if h.Neo4j != nil {
		results, err := h.queryByLanguage(ctx, language, label, query, repoID, limit)
		if err != nil {
			return nil, err
		}
		if len(results) > 0 {
			return results, nil
		}
	}
	return h.queryContentByLanguage(ctx, language, label, query, repoID, limit)
}

// buildLanguageCypher constructs the Cypher query and parameters for a
// language-specific entity lookup.
func buildLanguageCypher(language, label, query, repoID string, limit int) (string, map[string]any) {
	language = canonicalLanguage(language)
	params := map[string]any{
		"language": language,
		"limit":    limit,
	}

	// Build the extension filter for this language.
	exts := languageFileExtensions[language]
	extFilter := buildExtensionFilter(exts)

	switch label {
	case "Repository":
		return buildRepositoryCypher(language, query, repoID, limit)
	case "Directory":
		return buildDirectoryCypher(language, extFilter, query, repoID, params)
	case "File":
		return buildFileCypher(language, extFilter, query, repoID, params)
	default:
		return buildEntityCypher(language, label, extFilter, query, repoID, params)
	}
}

// buildRepositoryCypher returns a query for repositories that contain files
// in the given language.
func buildRepositoryCypher(language, query, repoID string, limit int) (string, map[string]any) {
	params := map[string]any{
		"language": language,
		"limit":    limit,
	}

	cypher := `
		MATCH (r:Repository)-[:REPO_CONTAINS]->(f:File)
		WHERE (f.language = $language OR f.language = $language_title)
	`
	params["language_title"] = strings.Title(language) //nolint:staticcheck

	if repoID != "" {
		cypher += " AND r.id = $repo_id"
		params["repo_id"] = repoID
	}
	if query != "" {
		cypher += " AND r.name CONTAINS $query"
		params["query"] = query
	}

	cypher += `
		WITH r, count(f) as file_count
		RETURN r.id as id, r.name as name,
		       coalesce(r.local_path, r.path) as local_path,
		       r.remote_url as remote_url,
		       file_count
		ORDER BY file_count DESC
		LIMIT $limit
	`
	return cypher, params
}

// buildDirectoryCypher returns a query for directories containing files in the
// given language.
func buildDirectoryCypher(language, extFilter, query, repoID string, params map[string]any) (string, map[string]any) {
	params["language_title"] = strings.Title(language) //nolint:staticcheck

	cypher := `
		MATCH (d:Directory)<-[:REPO_CONTAINS|CONTAINS*]-(r:Repository)
		MATCH (d)-[:CONTAINS]->(f:File)
		WHERE (f.language = $language OR f.language = $language_title` + extFilter + `)
	`

	if repoID != "" {
		cypher += " AND r.id = $repo_id"
		params["repo_id"] = repoID
	}
	if query != "" {
		cypher += " AND d.name CONTAINS $query"
		params["query"] = query
	}

	cypher += `
		WITH d, r, count(f) as file_count
		RETURN d.id as entity_id, d.name as name, labels(d) as labels,
		       d.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       file_count
		ORDER BY file_count DESC
		LIMIT $limit
	`
	return cypher, params
}

// buildFileCypher returns a query for files in the given language.
func buildFileCypher(language, extFilter, query, repoID string, params map[string]any) (string, map[string]any) {
	params["language_title"] = strings.Title(language) //nolint:staticcheck

	cypher := `
		MATCH (f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE (f.language = $language OR f.language = $language_title` + extFilter + `)
	`

	if repoID != "" {
		cypher += " AND r.id = $repo_id"
		params["repo_id"] = repoID
	}
	if query != "" {
		cypher += " AND f.name CONTAINS $query"
		params["query"] = query
	}

	cypher += `
		RETURN f.id as entity_id, f.name as name, labels(f) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       f.language as language
		ORDER BY f.relative_path
		LIMIT $limit
	`
	return cypher, params
}

// buildEntityCypher returns a query for code entities (Function, Class, etc.)
// in the given language.
func buildEntityCypher(language, label, extFilter, query, repoID string, params map[string]any) (string, map[string]any) {
	params["language_title"] = strings.Title(language) //nolint:staticcheck

	cypher := fmt.Sprintf(`
		MATCH (e:%s)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE (e.language = $language OR e.language = $language_title
		       OR f.language = $language OR f.language = $language_title%s)
	`, label, extFilter)

	if repoID != "" {
		cypher += " AND r.id = $repo_id"
		params["repo_id"] = repoID
	}
	if query != "" {
		cypher += " AND e.name CONTAINS $query"
		params["query"] = query
	}

	cypher += `
		RETURN e.id as entity_id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line, e.end_line as end_line
		ORDER BY f.relative_path, e.name
		LIMIT $limit
	`
	return cypher, params
}

// buildExtensionFilter returns a Cypher OR clause fragment that matches common
// file extensions for a language. Returns an empty string when no extensions
// are registered.
func buildExtensionFilter(exts []string) string {
	if len(exts) == 0 {
		return ""
	}
	clauses := make([]string, 0, len(exts))
	for _, ext := range exts {
		clauses = append(clauses, fmt.Sprintf("f.name ENDS WITH '%s'", ext))
	}
	return " OR " + strings.Join(clauses, " OR ")
}

// buildLanguageResult converts a Neo4j result row into the response shape.
func buildLanguageResult(row map[string]any, label string) map[string]any {
	result := map[string]any{
		"entity_id": StringVal(row, "entity_id"),
		"name":      StringVal(row, "name"),
	}

	if v := StringSliceVal(row, "labels"); v != nil {
		result["labels"] = v
	}
	if v := StringVal(row, "file_path"); v != "" {
		result["file_path"] = v
	}
	if v := StringVal(row, "repo_id"); v != "" {
		result["repo_id"] = v
	}
	if v := StringVal(row, "repo_name"); v != "" {
		result["repo_name"] = v
	}
	if v := StringVal(row, "language"); v != "" {
		result["language"] = v
	}

	switch label {
	case "Repository":
		result["id"] = StringVal(row, "id")
		result["name"] = StringVal(row, "name")
		result["local_path"] = StringVal(row, "local_path")
		result["remote_url"] = StringVal(row, "remote_url")
		result["file_count"] = IntVal(row, "file_count")
	case "Directory":
		result["file_count"] = IntVal(row, "file_count")
	default:
		if v := IntVal(row, "start_line"); v != 0 {
			result["start_line"] = v
		}
		if v := IntVal(row, "end_line"); v != 0 {
			result["end_line"] = v
		}
	}

	return result
}

// joinKeys returns a sorted comma-separated list of map keys.
func joinKeys[V any](m map[string]V) string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	// Sort for deterministic output.
	sortStrings(keys)
	return strings.Join(keys, ", ")
}

// sortStrings sorts a string slice in place (insertion sort for small slices).
func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j] < s[j-1]; j-- {
			s[j], s[j-1] = s[j-1], s[j]
		}
	}
}

// SupportedLanguages returns the set of language names with query support.
func SupportedLanguages() []string {
	return mapKeys(supportedLanguages)
}

// SupportedEntityTypes returns the set of entity type names with query support.
func SupportedEntityTypes() []string {
	return mapKeys(allSupportedEntityTypes())
}

// mapKeys returns sorted keys from a map.
func mapKeys[V any](m map[string]V) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sortStrings(keys)
	return keys
}
