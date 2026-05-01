package neo4j

import (
	"fmt"
	"strings"
)

func canonicalEntityRowNeedsSingletonFallback(row map[string]any) bool {
	return canonicalEntityValueContainsSubstring(row, "shortestpath") ||
		canonicalEntityValueContainsSubstring(row, "allshortestpaths") ||
		canonicalEntityRowHasCurlyBraceDefault(row)
}

func canonicalEntityValueContainsSubstring(value any, needle string) bool {
	switch typed := value.(type) {
	case string:
		return strings.Contains(strings.ToLower(typed), needle)
	case []string:
		for _, item := range typed {
			if canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	case []any:
		for _, item := range typed {
			if canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	case map[string]any:
		for key, item := range typed {
			if canonicalEntityValueContainsSubstring(key, needle) || canonicalEntityValueContainsSubstring(item, needle) {
				return true
			}
		}
	}
	return false
}

// canonicalEntityRowHasCurlyBraceDefault detects Terraform default map
// literals that can confuse NornicDB's grouped UNWIND parser as row metadata.
func canonicalEntityRowHasCurlyBraceDefault(row map[string]any) bool {
	props, ok := row["props"].(map[string]any)
	if !ok {
		return false
	}
	defaultValue, ok := props["default"].(string)
	if !ok {
		return false
	}
	return strings.Contains(defaultValue, "{") || strings.Contains(defaultValue, "}")
}

func canonicalNodeEntitySingletonWithContainmentStatement(
	label string,
	filePath string,
	row map[string]any,
	summary string,
	scopeID string,
	generationID string,
) Statement {
	if summary == "" {
		summary = fmt.Sprintf(
			"label=%s rows=1 entity_id=%v singleton_parameterized containment=inline",
			label,
			row["entity_id"],
		)
	}
	return Statement{
		Operation: OperationCanonicalUpsert,
		Cypher:    fmt.Sprintf(canonicalNodeEntitySingletonUpsertWithContainmentTemplate, label),
		Parameters: map[string]any{
			"file_path":                        filePath,
			"entity_id":                        row["entity_id"],
			"props":                            row["props"],
			"generation_id":                    row["generation_id"],
			StatementMetadataPhaseKey:          CanonicalPhaseEntities,
			StatementMetadataEntityLabelKey:    label,
			StatementMetadataPhaseGroupModeKey: PhaseGroupModeExecuteOnly,
			StatementMetadataSummaryKey:        summary,
			StatementMetadataScopeIDKey:        scopeID,
			StatementMetadataGenerationIDKey:   generationID,
		},
	}
}
