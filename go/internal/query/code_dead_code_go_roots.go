package query

import "strings"

func deadCodeIsGoHTTPHandlerRoot(result map[string]any, entity *EntityContent) bool {
	if strings.ToLower(deadCodeEntityLanguage(result, entity)) != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}

	source := deadCodeNormalizedSource(entity)
	return strings.Contains(source, "http.responsewriter") &&
		strings.Contains(source, "*http.request")
}

func deadCodeIsGoCLICommandRoot(result map[string]any, entity *EntityContent) bool {
	if strings.ToLower(deadCodeEntityLanguage(result, entity)) != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}

	source := deadCodeNormalizedSource(entity)
	return strings.Contains(source, "*cobra.command") &&
		strings.Contains(source, "[]string")
}

func deadCodeIsGoFrameworkCallbackRoot(result map[string]any, entity *EntityContent) bool {
	if strings.ToLower(deadCodeEntityLanguage(result, entity)) != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}
	if strings.TrimSpace(StringVal(result, "name")) != "Reconcile" {
		return false
	}

	source := deadCodeNormalizedSource(entity)
	if !strings.Contains(source, "context.context") {
		return false
	}
	if !strings.Contains(source, "request") {
		return false
	}

	return (strings.Contains(source, "ctrl.request") || strings.Contains(source, "reconcile.request")) &&
		(strings.Contains(source, "ctrl.result") || strings.Contains(source, "reconcile.result"))
}

func deadCodeNormalizedSource(entity *EntityContent) string {
	if entity == nil {
		return ""
	}
	normalized := strings.ToLower(entity.SourceCache)
	if normalized == "" {
		return ""
	}
	return strings.Join(strings.Fields(normalized), " ")
}
