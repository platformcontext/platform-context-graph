package query

import (
	"context"
	"fmt"
)

func (h *CodeHandler) enrichGraphSearchResultsWithContentMetadata(
	ctx context.Context,
	results []map[string]any,
	repoID string,
	query string,
	limit int,
) ([]map[string]any, error) {
	if h == nil || h.Content == nil || len(results) == 0 {
		return results, nil
	}

	rows, err := h.Content.SearchEntityContent(ctx, repoID, query, limit)
	if err != nil {
		return nil, fmt.Errorf("enrich graph search results with content metadata: %w", err)
	}
	if len(rows) == 0 {
		return results, nil
	}

	metadataByKey := make(map[string]map[string]any, len(rows))
	for _, row := range rows {
		metadataByKey[languageResultMatchKey(
			row.RelativePath,
			row.EntityType,
			row.EntityName,
			row.StartLine,
		)] = row.Metadata
	}

	for i := range results {
		entityType := resultContentEntityType(results[i])
		if entityType == "" {
			continue
		}
		key := languageResultMatchKey(
			StringVal(results[i], "file_path"),
			entityType,
			StringVal(results[i], "name"),
			IntVal(results[i], "start_line"),
		)
		metadata, ok := metadataByKey[key]
		if !ok || len(metadata) == 0 {
			continue
		}
		results[i]["metadata"] = metadata
		attachSemanticSummary(results[i])
	}

	return results, nil
}

func resultContentEntityType(result map[string]any) string {
	labels := StringSliceVal(result, "labels")
	for _, label := range labels {
		if entityType := graphLabelToContentEntityType(label); entityType != "" {
			return entityType
		}
	}
	return ""
}
