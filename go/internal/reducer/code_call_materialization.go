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

func buildCodeEntityIndex(envelopes []facts.Envelope) map[string]string {
	index := make(map[string]string)
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
			line := codeCallInt(item["line_number"], item["start_line"])
			if entityID == "" || line <= 0 {
				continue
			}
			for _, pathKey := range codeCallPathKeys(rawPath, relativePath) {
				index[codeCallPathLineKey(pathKey, line)] = entityID
			}
		}
	}
	return index
}

func resolveCodeEntityID(index map[string]string, pathValue any, lineValue any) string {
	line := codeCallInt(lineValue)
	if line <= 0 {
		return ""
	}

	for _, pathKey := range codeCallPathKeys(anyToString(pathValue), "") {
		if entityID := index[codeCallPathLineKey(pathKey, line)]; entityID != "" {
			return entityID
		}
	}
	return ""
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
