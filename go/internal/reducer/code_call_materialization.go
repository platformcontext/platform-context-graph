package reducer

import (
	"context"
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

const codeCallEvidenceSource = "parser/code-calls"

type codeEntityIndex struct {
	entitiesByPathLine map[string]string
	spansByPath        map[string][]codeFunctionSpan
	uniqueNameByPath   map[string]map[string]string
}

type codeFunctionSpan struct {
	startLine int
	endLine   int
	entityID  string
}

// CodeCallMaterializationHandler reduces one parser call-graph follow-up into
// canonical CALLS edge writes.
type CodeCallMaterializationHandler struct {
	FactLoader FactLoader
	EdgeWriter SharedProjectionEdgeWriter
}

// Handle executes the code-call materialization path.
func (h CodeCallMaterializationHandler) Handle(
	ctx context.Context,
	intent Intent,
) (Result, error) {
	if intent.Domain != DomainCodeCallMaterialization {
		return Result{}, fmt.Errorf(
			"code call materialization handler does not accept domain %q",
			intent.Domain,
		)
	}
	if h.FactLoader == nil {
		return Result{}, fmt.Errorf("code call materialization fact loader is required")
	}
	if h.EdgeWriter == nil {
		return Result{}, fmt.Errorf("code call materialization edge writer is required")
	}

	envelopes, err := h.FactLoader.ListFacts(ctx, intent.ScopeID, intent.GenerationID)
	if err != nil {
		return Result{}, fmt.Errorf("load facts for code call materialization: %w", err)
	}

	repositoryIDs, rows := ExtractCodeCallRows(envelopes)
	if len(repositoryIDs) == 0 {
		return Result{
			IntentID:        intent.IntentID,
			Domain:          DomainCodeCallMaterialization,
			Status:          ResultStatusSucceeded,
			EvidenceSummary: "no repositories available for code-call materialization",
		}, nil
	}

	if err := h.EdgeWriter.RetractEdges(
		ctx,
		DomainCodeCalls,
		buildCodeCallRetractRows(repositoryIDs),
		codeCallEvidenceSource,
	); err != nil {
		return Result{}, fmt.Errorf("retract canonical code calls: %w", err)
	}

	writeRows := buildCodeCallIntentRows(rows)
	if len(writeRows) > 0 {
		if err := h.EdgeWriter.WriteEdges(
			ctx,
			DomainCodeCalls,
			writeRows,
			codeCallEvidenceSource,
		); err != nil {
			return Result{}, fmt.Errorf("write canonical code calls: %w", err)
		}
	}

	return Result{
		IntentID: intent.IntentID,
		Domain:   DomainCodeCallMaterialization,
		Status:   ResultStatusSucceeded,
		EvidenceSummary: fmt.Sprintf(
			"materialized %d canonical code call edges across %d repositories",
			len(writeRows),
			len(repositoryIDs),
		),
		CanonicalWrites: len(writeRows),
	}, nil
}

// ExtractCodeCallRows builds canonical caller/callee edge rows from repository
// and file facts.
func ExtractCodeCallRows(envelopes []facts.Envelope) ([]string, []map[string]any) {
	if len(envelopes) == 0 {
		return nil, nil
	}

	repositoryIDs := collectCodeCallRepositoryIDs(envelopes)
	if len(repositoryIDs) == 0 {
		return nil, nil
	}

	entityIndex := buildCodeEntityIndex(envelopes)
	seenRows := make(map[string]struct{})
	rows := make([]map[string]any, 0)

	for _, env := range envelopes {
		if env.FactKind != "file" {
			continue
		}

		repositoryID := payloadStr(env.Payload, "repo_id")
		if repositoryID == "" {
			continue
		}

		fileData, ok := env.Payload["parsed_file_data"].(map[string]any)
		if !ok {
			continue
		}
		relativePath := payloadStr(env.Payload, "relative_path")

		rows = append(rows, extractSCIPCodeCallRows(repositoryID, entityIndex, seenRows, fileData)...)
		rows = append(
			rows,
			extractGenericCodeCallRows(
				repositoryID,
				relativePath,
				anyToString(fileData["path"]),
				entityIndex,
				seenRows,
				fileData,
			)...,
		)
	}

	sort.Slice(rows, func(i, j int) bool {
		left := anyToString(rows[i]["caller_entity_id"]) + "->" + anyToString(rows[i]["callee_entity_id"])
		right := anyToString(rows[j]["caller_entity_id"]) + "->" + anyToString(rows[j]["callee_entity_id"])
		if left == right {
			return anyToString(rows[i]["repo_id"]) < anyToString(rows[j]["repo_id"])
		}
		return left < right
	})

	return repositoryIDs, rows
}

func collectCodeCallRepositoryIDs(envelopes []facts.Envelope) []string {
	repositorySet := make(map[string]struct{})
	for _, env := range envelopes {
		switch env.FactKind {
		case "repository", "file":
			repositoryID := payloadStr(env.Payload, "repo_id")
			if repositoryID == "" {
				repositoryID = payloadStr(env.Payload, "graph_id")
			}
			if repositoryID != "" {
				repositorySet[repositoryID] = struct{}{}
			}
		}
	}

	repositoryIDs := make([]string, 0, len(repositorySet))
	for repositoryID := range repositorySet {
		repositoryIDs = append(repositoryIDs, repositoryID)
	}
	sort.Strings(repositoryIDs)
	return repositoryIDs
}

func buildCodeEntityIndex(envelopes []facts.Envelope) codeEntityIndex {
	index := codeEntityIndex{
		entitiesByPathLine: make(map[string]string),
		spansByPath:        make(map[string][]codeFunctionSpan),
		uniqueNameByPath:   make(map[string]map[string]string),
	}
	nameCandidates := make(map[string]map[string]map[string]struct{})

	for _, env := range envelopes {
		if env.FactKind != "file" {
			continue
		}

		fileData, ok := env.Payload["parsed_file_data"].(map[string]any)
		if !ok {
			continue
		}

		relativePath := payloadStr(env.Payload, "relative_path")
		rawPath := anyToString(fileData["path"])
		for _, item := range mapSlice(fileData["functions"]) {
			entityID := anyToString(item["uid"])
			name := strings.TrimSpace(anyToString(item["name"]))
			startLine := codeCallInt(item["line_number"], item["start_line"])
			endLine := codeCallInt(item["end_line"])
			if entityID == "" || startLine <= 0 {
				continue
			}
			if endLine < startLine {
				endLine = startLine
			}
			for _, pathKey := range codeCallPathKeys(rawPath, relativePath) {
				index.entitiesByPathLine[codeCallPathLineKey(pathKey, startLine)] = entityID
				index.spansByPath[pathKey] = append(index.spansByPath[pathKey], codeFunctionSpan{
					startLine: startLine,
					endLine:   endLine,
					entityID:  entityID,
				})
				if name == "" {
					continue
				}
				if _, ok := nameCandidates[pathKey]; !ok {
					nameCandidates[pathKey] = make(map[string]map[string]struct{})
				}
				if _, ok := nameCandidates[pathKey][name]; !ok {
					nameCandidates[pathKey][name] = make(map[string]struct{})
				}
				nameCandidates[pathKey][name][entityID] = struct{}{}
			}
		}
	}

	for pathKey, spans := range index.spansByPath {
		sort.Slice(spans, func(i, j int) bool {
			if spans[i].startLine == spans[j].startLine {
				return spans[i].endLine < spans[j].endLine
			}
			return spans[i].startLine < spans[j].startLine
		})
		index.spansByPath[pathKey] = spans
	}
	for pathKey, names := range nameCandidates {
		index.uniqueNameByPath[pathKey] = make(map[string]string, len(names))
		for name, entityIDs := range names {
			if len(entityIDs) != 1 {
				continue
			}
			for entityID := range entityIDs {
				index.uniqueNameByPath[pathKey][name] = entityID
			}
		}
	}
	return index
}

func resolveCodeEntityID(index codeEntityIndex, pathValue any, lineValue any) string {
	line := codeCallInt(lineValue)
	if line <= 0 {
		return ""
	}

	for _, pathKey := range codeCallPathKeys(anyToString(pathValue), "") {
		if entityID := index.entitiesByPathLine[codeCallPathLineKey(pathKey, line)]; entityID != "" {
			return entityID
		}
	}
	return ""
}

func extractSCIPCodeCallRows(
	repositoryID string,
	entityIndex codeEntityIndex,
	seenRows map[string]struct{},
	fileData map[string]any,
) []map[string]any {
	rows := make([]map[string]any, 0)
	for _, edge := range mapSlice(fileData["function_calls_scip"]) {
		callerID := resolveCodeEntityID(entityIndex, edge["caller_file"], edge["caller_line"])
		calleeID := resolveCodeEntityID(entityIndex, edge["callee_file"], edge["callee_line"])
		if callerID == "" || calleeID == "" {
			continue
		}

		key := repositoryID + "|" + callerID + "|" + calleeID
		if _, exists := seenRows[key]; exists {
			continue
		}
		seenRows[key] = struct{}{}

		row := map[string]any{
			"repo_id":          repositoryID,
			"caller_entity_id": callerID,
			"callee_entity_id": calleeID,
			"action":           IntentActionUpsert,
		}
		copyOptionalCodeCallField(row, edge, "caller_symbol")
		copyOptionalCodeCallField(row, edge, "callee_symbol")
		copyOptionalCodeCallField(row, edge, "caller_file")
		copyOptionalCodeCallField(row, edge, "callee_file")
		copyOptionalCodeCallField(row, edge, "ref_line")
		rows = append(rows, row)
	}
	return rows
}

func extractGenericCodeCallRows(
	repositoryID string,
	relativePath string,
	rawPath string,
	entityIndex codeEntityIndex,
	seenRows map[string]struct{},
	fileData map[string]any,
) []map[string]any {
	rows := make([]map[string]any, 0)
	filePath := codeCallPreferredPath(rawPath, relativePath)
	for _, edge := range mapSlice(fileData["function_calls"]) {
		callLine := codeCallInt(edge["line_number"], edge["ref_line"])
		if callLine <= 0 {
			continue
		}
		callerID := resolveContainingCodeEntityID(entityIndex, rawPath, relativePath, callLine)
		if callerID == "" {
			continue
		}
		calleeID := resolveSameFileCalleeEntityID(entityIndex, rawPath, relativePath, edge)
		if calleeID == "" {
			continue
		}

		key := repositoryID + "|" + callerID + "|" + calleeID
		if _, exists := seenRows[key]; exists {
			continue
		}
		seenRows[key] = struct{}{}

		row := map[string]any{
			"repo_id":          repositoryID,
			"caller_entity_id": callerID,
			"callee_entity_id": calleeID,
			"caller_file":      filePath,
			"callee_file":      filePath,
			"ref_line":         callLine,
			"action":           IntentActionUpsert,
		}
		rows = append(rows, row)
	}
	return rows
}

func resolveContainingCodeEntityID(
	index codeEntityIndex,
	rawPath string,
	relativePath string,
	line int,
) string {
	var (
		bestEntityID string
		bestWidth    int
	)
	for _, pathKey := range codeCallPathKeys(rawPath, relativePath) {
		for _, span := range index.spansByPath[pathKey] {
			if line < span.startLine || line > span.endLine {
				continue
			}
			width := span.endLine - span.startLine
			if bestEntityID == "" || width < bestWidth {
				bestEntityID = span.entityID
				bestWidth = width
			}
		}
		if bestEntityID != "" {
			return bestEntityID
		}
	}
	return ""
}

func resolveSameFileCalleeEntityID(
	index codeEntityIndex,
	rawPath string,
	relativePath string,
	call map[string]any,
) string {
	for _, name := range codeCallCandidateNames(call) {
		for _, pathKey := range codeCallPathKeys(rawPath, relativePath) {
			if entityID := index.uniqueNameByPath[pathKey][name]; entityID != "" {
				return entityID
			}
		}
	}
	return ""
}

func codeCallCandidateNames(call map[string]any) []string {
	names := make([]string, 0, 2)
	appendName := func(value string) {
		trimmed := strings.TrimSpace(value)
		if trimmed == "" {
			return
		}
		for _, existing := range names {
			if existing == trimmed {
				return
			}
		}
		names = append(names, trimmed)
	}

	appendName(anyToString(call["name"]))
	fullName := anyToString(call["full_name"])
	appendName(fullName)
	appendName(codeCallTrailingName(fullName))
	return names
}

func codeCallTrailingName(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	cutset := func(r rune) bool {
		switch r {
		case '.', ':', '#', '/', '\\':
			return true
		default:
			return false
		}
	}
	parts := strings.FieldsFunc(trimmed, cutset)
	if len(parts) == 0 {
		return ""
	}
	return parts[len(parts)-1]
}

func codeCallPreferredPath(rawPath string, relativePath string) string {
	if normalized := normalizeCodeCallPath(relativePath); normalized != "" {
		return normalized
	}
	return normalizeCodeCallPath(rawPath)
}

func codeCallPathKeys(rawPath string, relativePath string) []string {
	keys := make([]string, 0, 4)
	appendKey := func(value string) {
		normalized := normalizeCodeCallPath(value)
		if normalized == "" {
			return
		}
		for _, existing := range keys {
			if existing == normalized {
				return
			}
		}
		keys = append(keys, normalized)
	}

	appendKey(rawPath)
	appendKey(relativePath)
	if rawPath != "" {
		appendKey(filepath.Base(rawPath))
	}
	if relativePath != "" {
		appendKey(filepath.Base(relativePath))
	}
	return keys
}

func normalizeCodeCallPath(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	return filepath.ToSlash(filepath.Clean(trimmed))
}

func codeCallPathLineKey(path string, line int) string {
	return fmt.Sprintf("%s#%d", path, line)
}

func mapSlice(value any) []map[string]any {
	switch typed := value.(type) {
	case []map[string]any:
		return typed
	case []any:
		result := make([]map[string]any, 0, len(typed))
		for _, item := range typed {
			asMap, ok := item.(map[string]any)
			if ok {
				result = append(result, asMap)
			}
		}
		return result
	default:
		return nil
	}
}

func codeCallInt(values ...any) int {
	for _, value := range values {
		switch typed := value.(type) {
		case int:
			return typed
		case int32:
			return int(typed)
		case int64:
			return int(typed)
		case float32:
			return int(typed)
		case float64:
			return int(typed)
		}
	}
	return 0
}

func copyOptionalCodeCallField(dst map[string]any, src map[string]any, key string) {
	if value, ok := src[key]; ok && value != nil {
		dst[key] = value
	}
}

func buildCodeCallRetractRows(repositoryIDs []string) []SharedProjectionIntentRow {
	rows := make([]SharedProjectionIntentRow, 0, len(repositoryIDs))
	for _, repositoryID := range repositoryIDs {
		rows = append(rows, SharedProjectionIntentRow{RepositoryID: repositoryID})
	}
	return rows
}

func buildCodeCallIntentRows(rows []map[string]any) []SharedProjectionIntentRow {
	intents := make([]SharedProjectionIntentRow, 0, len(rows))
	for _, row := range rows {
		callerID := anyToString(row["caller_entity_id"])
		calleeID := anyToString(row["callee_entity_id"])
		intents = append(intents, SharedProjectionIntentRow{
			ProjectionDomain: DomainCodeCalls,
			PartitionKey:     callerID + "->" + calleeID,
			RepositoryID:     anyToString(row["repo_id"]),
			Payload:          copyPayload(row),
		})
	}
	return intents
}
