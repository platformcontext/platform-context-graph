package query

import (
	"context"
	"net/http"
	"path/filepath"
	"slices"
	"strings"
	"unicode"
)

type deadCodeRequest struct {
	RepoID               string   `json:"repo_id"`
	ExcludeDecoratedWith []string `json:"exclude_decorated_with"`
}

// handleDeadCode finds graph-backed dead-code candidates and then applies the
// current default reachability policy before returning a derived result.
func (h *CodeHandler) handleDeadCode(w http.ResponseWriter, r *http.Request) {
	if capabilityUnsupported(h.profile(), "code_quality.dead_code") {
		WriteContractError(
			w,
			r,
			http.StatusNotImplemented,
			"dead code analysis requires authoritative graph mode",
			ErrorCodeUnsupportedCapability,
			"code_quality.dead_code",
			h.profile(),
			requiredProfile("code_quality.dead_code"),
		)
		return
	}

	var req deadCodeRequest
	if err := ReadJSON(r, &req); err != nil {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	resolvedRepoID, err := h.resolveRepositorySelector(r.Context(), req.RepoID)
	if err != nil && strings.TrimSpace(req.RepoID) != "" {
		WriteError(w, http.StatusBadRequest, err.Error())
		return
	}
	req.RepoID = resolvedRepoID

	rows, err := h.Neo4j.Run(r.Context(), deadCodeGraphCypher(req.RepoID != ""), deadCodeGraphParams(req.RepoID))
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}

	results, contentByID, err := h.buildDeadCodeResults(r.Context(), rows)
	if err != nil {
		WriteError(w, http.StatusInternalServerError, err.Error())
		return
	}
	results = filterDeadCodeResultsByDefaultPolicy(results, contentByID)
	results = filterResultsByDecoratorExclusions(results, req.ExcludeDecoratedWith)

	WriteSuccess(w, r, http.StatusOK, map[string]any{
		"repo_id":  req.RepoID,
		"results":  results,
		"analysis": buildDeadCodeAnalysis(results, req.ExcludeDecoratedWith),
	}, BuildTruthEnvelope(h.profile(), "code_quality.dead_code", TruthBasisHybrid, "resolved from graph-backed dead-code candidates with partial root modeling"))
}

func deadCodeGraphCypher(hasRepoID bool) string {
	cypher := `
		MATCH (e)<-[:CONTAINS]-(f:File)<-[:REPO_CONTAINS]-(r:Repository)
		WHERE NOT ()-[:CALLS|IMPORTS|REFERENCES]->(e)
	`
	if hasRepoID {
		cypher += ` AND r.id = $repo_id`
	}
	cypher += `
		RETURN e.id as entity_id, e.name as name, labels(e) as labels,
		       f.relative_path as file_path,
		       r.id as repo_id, r.name as repo_name,
		       coalesce(e.language, f.language) as language,
		       e.start_line as start_line,
		       e.end_line as end_line,
` + graphSemanticMetadataProjection() + `
		ORDER BY f.relative_path, e.name
		LIMIT 100
	`
	return cypher
}

func deadCodeGraphParams(repoID string) map[string]any {
	if strings.TrimSpace(repoID) == "" {
		return map[string]any{}
	}
	return map[string]any{"repo_id": strings.TrimSpace(repoID)}
}

func (h *CodeHandler) buildDeadCodeResults(
	ctx context.Context,
	rows []map[string]any,
) ([]map[string]any, map[string]*EntityContent, error) {
	results := make([]map[string]any, 0, len(rows))
	for _, row := range rows {
		result := map[string]any{
			"entity_id":  StringVal(row, "entity_id"),
			"name":       StringVal(row, "name"),
			"labels":     StringSliceVal(row, "labels"),
			"file_path":  StringVal(row, "file_path"),
			"repo_id":    StringVal(row, "repo_id"),
			"repo_name":  StringVal(row, "repo_name"),
			"language":   StringVal(row, "language"),
			"start_line": IntVal(row, "start_line"),
			"end_line":   IntVal(row, "end_line"),
		}
		if metadata := graphResultMetadata(row); len(metadata) > 0 {
			result["metadata"] = metadata
		}
		results = append(results, result)
	}

	return h.enrichDeadCodeResultsWithContent(ctx, results)
}

func (h *CodeHandler) enrichDeadCodeResultsWithContent(
	ctx context.Context,
	results []map[string]any,
) ([]map[string]any, map[string]*EntityContent, error) {
	contentByID := make(map[string]*EntityContent, len(results))
	if len(results) == 0 {
		return results, contentByID, nil
	}

	for i := range results {
		if metadata, ok := results[i]["metadata"].(map[string]any); ok && len(metadata) > 0 {
			attachSemanticSummary(results[i])
		}
	}
	if h == nil || h.Content == nil {
		return results, contentByID, nil
	}

	for i := range results {
		entityID := StringVal(results[i], "entity_id")
		if entityID == "" {
			continue
		}
		entity, err := h.Content.GetEntityContent(ctx, entityID)
		if err != nil {
			return nil, nil, err
		}
		if entity == nil {
			continue
		}
		contentByID[entityID] = entity
		if len(entity.Metadata) == 0 {
			continue
		}
		results[i]["metadata"] = mergeGraphAndContentMetadata(results[i]["metadata"], entity.Metadata)
		attachSemanticSummary(results[i])
	}

	return results, contentByID, nil
}

func filterDeadCodeResultsByDefaultPolicy(
	results []map[string]any,
	contentByID map[string]*EntityContent,
) []map[string]any {
	if len(results) == 0 {
		return results
	}

	filtered := make([]map[string]any, 0, len(results))
	for _, result := range results {
		entityID := StringVal(result, "entity_id")
		if deadCodeResultExcludedByDefault(result, contentByID[entityID]) {
			continue
		}
		filtered = append(filtered, result)
	}
	return filtered
}

func deadCodeResultExcludedByDefault(result map[string]any, entity *EntityContent) bool {
	return deadCodeIsLanguageEntrypoint(result, entity) ||
		deadCodeIsLibraryPublicAPIRoot(result, entity) ||
		deadCodeIsTestFile(result, entity) ||
		deadCodeIsGeneratedCode(result, entity)
}

func deadCodeIsLanguageEntrypoint(result map[string]any, entity *EntityContent) bool {
	if primaryEntityLabel(result) != "Function" {
		return false
	}

	name := strings.TrimSpace(StringVal(result, "name"))
	language := strings.ToLower(deadCodeEntityLanguage(result, entity))
	switch language {
	case "go":
		return name == "main" || name == "init"
	case "python":
		return name == "__main__"
	default:
		return false
	}
}

func deadCodeIsLibraryPublicAPIRoot(result map[string]any, entity *EntityContent) bool {
	if strings.ToLower(deadCodeEntityLanguage(result, entity)) != "go" {
		return false
	}
	if !deadCodeIsSupportedGoPublicAPIEntity(result, entity) {
		return false
	}

	path := strings.ToLower(deadCodeEntityPath(result, entity))
	switch {
	case path == "",
		strings.HasPrefix(path, "cmd/"),
		strings.Contains(path, "/cmd/"),
		strings.HasPrefix(path, "internal/"),
		strings.Contains(path, "/internal/"),
		strings.HasPrefix(path, "vendor/"),
		strings.Contains(path, "/vendor/"):
		return false
	}

	name := strings.TrimSpace(StringVal(result, "name"))
	if name == "" {
		return false
	}
	for _, r := range name {
		return unicode.IsUpper(r)
	}
	return false
}

func deadCodeIsSupportedGoPublicAPIEntity(result map[string]any, entity *EntityContent) bool {
	switch primaryEntityLabel(result) {
	case "Function", "Struct", "Interface", "Class":
		return true
	}
	if entity == nil {
		return false
	}
	switch strings.TrimSpace(entity.EntityType) {
	case "Function", "Struct", "Interface", "Class":
		return true
	default:
		return false
	}
}

func deadCodeIsTestFile(result map[string]any, entity *EntityContent) bool {
	path := strings.ToLower(deadCodeEntityPath(result, entity))
	base := filepath.Base(path)
	switch {
	case strings.HasSuffix(path, "_test.go"):
		return true
	case strings.Contains(path, "/__tests__/"),
		strings.Contains(path, "/tests/"),
		strings.Contains(path, "/test/"):
		return true
	case strings.HasPrefix(base, "test_"),
		strings.HasSuffix(base, "_test.py"),
		strings.HasSuffix(base, ".test.js"),
		strings.HasSuffix(base, ".test.jsx"),
		strings.HasSuffix(base, ".test.ts"),
		strings.HasSuffix(base, ".test.tsx"),
		strings.HasSuffix(base, ".spec.js"),
		strings.HasSuffix(base, ".spec.jsx"),
		strings.HasSuffix(base, ".spec.ts"),
		strings.HasSuffix(base, ".spec.tsx"):
		return true
	default:
		return false
	}
}

func deadCodeIsGeneratedCode(result map[string]any, entity *EntityContent) bool {
	path := strings.ToLower(deadCodeEntityPath(result, entity))
	base := filepath.Base(path)
	switch {
	case strings.Contains(path, "/gen/"),
		strings.Contains(path, "/generated/"),
		strings.Contains(path, "/.generated/"),
		strings.HasSuffix(base, ".pb.go"),
		strings.HasSuffix(base, ".gen.go"),
		strings.HasSuffix(base, "_generated.go"):
		return true
	}

	source := ""
	if entity != nil {
		source = strings.ToLower(entity.SourceCache)
	}
	return strings.Contains(source, "code generated by") ||
		strings.Contains(source, "do not edit") ||
		strings.Contains(source, "@generated")
}

func deadCodeEntityPath(result map[string]any, entity *EntityContent) string {
	if entity != nil && strings.TrimSpace(entity.RelativePath) != "" {
		return filepath.ToSlash(entity.RelativePath)
	}
	return filepath.ToSlash(StringVal(result, "file_path"))
}

func deadCodeEntityLanguage(result map[string]any, entity *EntityContent) string {
	if entity != nil && strings.TrimSpace(entity.Language) != "" {
		return entity.Language
	}
	return StringVal(result, "language")
}

func buildDeadCodeAnalysis(results []map[string]any, excluded []string) map[string]any {
	frameworks := make([]string, 0)
	seenFrameworks := make(map[string]struct{})
	for _, result := range results {
		metadata, _ := result["metadata"].(map[string]any)
		framework := strings.TrimSpace(StringVal(metadata, "framework"))
		if framework == "" {
			continue
		}
		if _, ok := seenFrameworks[framework]; ok {
			continue
		}
		seenFrameworks[framework] = struct{}{}
		frameworks = append(frameworks, framework)
	}
	slices.Sort(frameworks)

	return map[string]any{
		"root_categories_used":    []string{"language_entrypoints", "generated_and_tool_owned", "library_public_api"},
		"frameworks_recognized":   frameworks,
		"reflection_modeled":      false,
		"tests_excluded":          true,
		"generated_code_excluded": true,
		"user_overrides_applied":  len(excluded) > 0,
		"modeled_entrypoints":     []string{"go.main", "go.init", "python.__main__"},
		"modeled_public_api":      []string{"go.exported_non_internal_package_symbol"},
		"notes": []string{
			"dead-code remains derived until broader framework, public-API, and reflection root models land",
			"go exported symbols outside cmd/, internal/, and vendor/ are treated as public API roots by default",
		},
	}
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
