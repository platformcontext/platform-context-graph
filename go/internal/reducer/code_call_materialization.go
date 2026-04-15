package reducer

import (
	"context"
	"fmt"
	"sort"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

const (
	codeCallEvidenceSource         = "parser/code-calls"
	pythonMetaclassEvidenceSource = "parser/python-metaclass"
)

// CodeCallMaterializationHandler reduces one parser relationship follow-up into
// canonical code-edge writes.
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

	codeCallRepoIDs, codeCallRows, metaclassRepoIDs, metaclassRows := ExtractAllCodeRelationshipRows(envelopes)
	repositoryIDs := mergeCodeRelationshipRepositoryIDs(codeCallRepoIDs, metaclassRepoIDs)
	if len(repositoryIDs) == 0 {
		return Result{
			IntentID:        intent.IntentID,
			Domain:          DomainCodeCallMaterialization,
			Status:          ResultStatusSucceeded,
			EvidenceSummary: "no repositories available for code relationship materialization",
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

	writeRows := buildCodeRelationshipIntentRows(codeCallRows)
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
	metaclassWriteRows := buildCodeRelationshipIntentRows(metaclassRows)
	if len(metaclassWriteRows) > 0 {
		if err := h.EdgeWriter.WriteEdges(
			ctx,
			DomainCodeCalls,
			metaclassWriteRows,
			pythonMetaclassEvidenceSource,
		); err != nil {
			return Result{}, fmt.Errorf("write canonical python metaclass edges: %w", err)
		}
	}

	return Result{
		IntentID: intent.IntentID,
		Domain:   DomainCodeCallMaterialization,
		Status:   ResultStatusSucceeded,
		EvidenceSummary: fmt.Sprintf(
			"materialized %d canonical code relationship edges across %d repositories",
			len(writeRows)+len(metaclassWriteRows),
			len(repositoryIDs),
		),
		CanonicalWrites: len(writeRows) + len(metaclassWriteRows),
	}, nil
}

// ExtractAllCodeRelationshipRows builds both code-call and metaclass edge rows
// from a single entity index pass. This eliminates the duplicate
// buildCodeEntityIndex call that occurs when ExtractCodeCallRows and
// ExtractPythonMetaclassRows are called separately.
func ExtractAllCodeRelationshipRows(envelopes []facts.Envelope) (
	codeCallRepoIDs []string,
	codeCallRows []map[string]any,
	metaclassRepoIDs []string,
	metaclassRows []map[string]any,
) {
	if len(envelopes) == 0 {
		return nil, nil, nil, nil
	}

	repositoryIDs := collectCodeCallRepositoryIDs(envelopes)
	if len(repositoryIDs) == 0 {
		return nil, nil, nil, nil
	}

	entityIndex := buildCodeEntityIndex(envelopes)
	repositoryImports := collectCodeCallRepositoryImports(envelopes)

	ccRepoIDs, ccRows := extractCodeCallRowsWithIndex(envelopes, repositoryIDs, entityIndex, repositoryImports)
	mcRepoIDs, mcRows := extractPythonMetaclassRowsWithIndex(envelopes, repositoryIDs, entityIndex, repositoryImports)
	return ccRepoIDs, ccRows, mcRepoIDs, mcRows
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
	repositoryImports := collectCodeCallRepositoryImports(envelopes)
	return extractCodeCallRowsWithIndex(envelopes, repositoryIDs, entityIndex, repositoryImports)
}

func extractCodeCallRowsWithIndex(
	envelopes []facts.Envelope,
	repositoryIDs []string,
	entityIndex codeEntityIndex,
	repositoryImports map[string]map[string][]string,
) ([]string, []map[string]any) {
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
				repositoryImports[repositoryID],
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
