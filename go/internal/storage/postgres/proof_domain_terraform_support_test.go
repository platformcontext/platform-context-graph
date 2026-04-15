package postgres

import (
	"encoding/json"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func cloneEvidenceFacts(input map[string]evidenceRecord) map[string]evidenceRecord {
	cloned := make(map[string]evidenceRecord, len(input))
	for key, value := range input {
		if value.details != nil {
			details := make(map[string]any, len(value.details))
			for detailKey, detailValue := range value.details {
				details[detailKey] = detailValue
			}
			value.details = details
		}
		cloned[key] = value
	}
	return cloned
}

func proofFactRows(input map[string]facts.Envelope, scopeID, generationID string) [][]any {
	rows := [][]any{}
	for _, envelope := range input {
		if envelope.ScopeID != scopeID || envelope.GenerationID != generationID {
			continue
		}
		payload, _ := json.Marshal(envelope.Payload)
		rows = append(rows, []any{
			envelope.FactID,
			envelope.ScopeID,
			envelope.GenerationID,
			envelope.FactKind,
			envelope.StableFactKey,
			envelope.SourceRef.SourceSystem,
			envelope.SourceRef.FactKey,
			envelope.SourceRef.SourceURI,
			envelope.SourceRef.SourceRecordID,
			envelope.ObservedAt.UTC(),
			envelope.IsTombstone,
			payload,
		})
	}
	return rows
}

func proofRepositoryCatalogRows(input map[string]facts.Envelope) [][]any {
	rows := make([][]any, 0, len(input))
	seen := make(map[string]struct{})
	for _, envelope := range input {
		if envelope.FactKind != "repository" {
			continue
		}
		repoID := catalogString(envelope.Payload, "repo_id", "graph_id", "name")
		if repoID == "" {
			continue
		}
		if _, exists := seen[repoID]; exists {
			continue
		}
		seen[repoID] = struct{}{}
		payload, _ := json.Marshal(envelope.Payload)
		rows = append(rows, []any{payload})
	}
	return rows
}
