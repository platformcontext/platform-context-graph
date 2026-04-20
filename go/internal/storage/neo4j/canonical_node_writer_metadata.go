package neo4j

import "strings"

func canonicalTypeScriptClassFamilyMetadata(row map[string]any) map[string]any {
	metadata, ok := row["entity_metadata"].(map[string]any)
	if !ok || len(metadata) == 0 {
		return nil
	}

	language := canonicalMetadataString(row, "language")
	if language != "typescript" && language != "tsx" {
		return nil
	}

	label := canonicalMetadataString(row, "label")
	switch label {
	case "Class", "Interface", "Enum":
	default:
		return nil
	}

	result := map[string]any{}
	if decorators := canonicalMetadataStringSlice(metadata, "decorators"); len(decorators) > 0 {
		result["decorators"] = decorators
	}
	if typeParameters := canonicalMetadataStringSlice(metadata, "type_parameters"); len(typeParameters) > 0 {
		result["type_parameters"] = typeParameters
	}
	if group := canonicalMetadataString(metadata, "declaration_merge_group"); group != "" {
		result["declaration_merge_group"] = group
	}
	if count := canonicalMetadataInt(metadata, "declaration_merge_count"); count > 0 {
		result["declaration_merge_count"] = count
	}
	if kinds := canonicalMetadataStringSlice(metadata, "declaration_merge_kinds"); len(kinds) > 0 {
		result["declaration_merge_kinds"] = kinds
	}
	if len(result) == 0 {
		return nil
	}
	return result
}

func canonicalMetadataString(row map[string]any, key string) string {
	value, ok := row[key]
	if !ok || value == nil {
		return ""
	}
	text, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(text)
}

func canonicalMetadataStringSlice(metadata map[string]any, key string) []string {
	value, ok := metadata[key]
	if !ok || value == nil {
		return nil
	}

	switch typed := value.(type) {
	case []string:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			if trimmed := strings.TrimSpace(item); trimmed != "" {
				out = append(out, trimmed)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	case []any:
		out := make([]string, 0, len(typed))
		for _, item := range typed {
			text, ok := item.(string)
			if !ok {
				continue
			}
			if trimmed := strings.TrimSpace(text); trimmed != "" {
				out = append(out, trimmed)
			}
		}
		if len(out) == 0 {
			return nil
		}
		return out
	default:
		return nil
	}
}

func canonicalMetadataInt(metadata map[string]any, key string) int {
	value, ok := metadata[key]
	if !ok || value == nil {
		return 0
	}

	switch typed := value.(type) {
	case int:
		return typed
	case int8:
		return int(typed)
	case int16:
		return int(typed)
	case int32:
		return int(typed)
	case int64:
		return int(typed)
	case float32:
		return int(typed)
	case float64:
		return int(typed)
	default:
		return 0
	}
}
