package reducer

import "strings"

func inheritancePayloadTraitAdaptations(payload map[string]any) []string {
	return semanticPayloadMetadataStringSlice(payload, "trait_adaptations")
}

func inheritanceTraitOverrideTargets(adaptation string) []string {
	trimmed := strings.TrimSpace(adaptation)
	if trimmed == "" {
		return nil
	}

	lower := strings.ToLower(trimmed)
	key := " insteadof "
	index := strings.Index(lower, key)
	if index < 0 {
		return nil
	}

	tail := strings.TrimSpace(trimmed[index+len(key):])
	if tail == "" {
		return nil
	}

	parts := strings.Split(tail, ",")
	targets := make([]string, 0, len(parts))
	for _, part := range parts {
		if target := inheritanceTraitName(part); target != "" {
			targets = append(targets, target)
		}
	}
	return dedupeNonEmptyStrings(targets)
}

func inheritanceTraitName(raw string) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}

	if index := strings.LastIndex(trimmed, `\`); index >= 0 {
		trimmed = trimmed[index+1:]
	}

	return strings.TrimSpace(trimmed)
}
