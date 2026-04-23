package query

import "strings"

type deadCodePolicyStats struct {
	RootsSkippedMissingSource int
}

type deadCodeGoPolicyContext struct {
	language         string
	normalizedSource string
}

func newDeadCodeGoPolicyContext(result map[string]any, entity *EntityContent) deadCodeGoPolicyContext {
	return deadCodeGoPolicyContext{
		language:         strings.ToLower(deadCodeEntityLanguage(result, entity)),
		normalizedSource: deadCodeNormalizedSource(entity),
	}
}

func deadCodeIsGoHTTPHandlerRoot(result map[string]any, policy deadCodeGoPolicyContext) bool {
	if policy.language != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}

	return strings.Contains(policy.normalizedSource, "http.responsewriter") &&
		strings.Contains(policy.normalizedSource, "*http.request")
}

func deadCodeIsGoCLICommandRoot(result map[string]any, policy deadCodeGoPolicyContext) bool {
	if policy.language != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}

	return strings.Contains(policy.normalizedSource, "*cobra.command") &&
		strings.Contains(policy.normalizedSource, "[]string")
}

func deadCodeIsGoFrameworkCallbackRoot(result map[string]any, policy deadCodeGoPolicyContext) bool {
	if policy.language != "go" {
		return false
	}
	if primaryEntityLabel(result) != "Function" {
		return false
	}
	if strings.TrimSpace(StringVal(result, "name")) != "Reconcile" {
		return false
	}

	if !strings.Contains(policy.normalizedSource, "context.context") {
		return false
	}
	if !strings.Contains(policy.normalizedSource, "request") {
		return false
	}

	return (strings.Contains(policy.normalizedSource, "ctrl.request") || strings.Contains(policy.normalizedSource, "reconcile.request")) &&
		(strings.Contains(policy.normalizedSource, "ctrl.result") || strings.Contains(policy.normalizedSource, "reconcile.result"))
}

func deadCodeNormalizedSource(entity *EntityContent) string {
	if entity == nil {
		return ""
	}
	normalized := strings.ToLower(stripGoComments(entity.SourceCache))
	if normalized == "" {
		return ""
	}
	return strings.Join(strings.Fields(normalized), " ")
}

func stripGoComments(source string) string {
	if source == "" {
		return ""
	}

	var out strings.Builder
	out.Grow(len(source))
	for i := 0; i < len(source); {
		switch {
		case i+1 < len(source) && source[i] == '/' && source[i+1] == '/':
			i += 2
			for i < len(source) && source[i] != '\n' {
				i++
			}
		case i+1 < len(source) && source[i] == '/' && source[i+1] == '*':
			i += 2
			for i+1 < len(source) && !(source[i] == '*' && source[i+1] == '/') {
				i++
			}
			if i+1 < len(source) {
				i += 2
			} else {
				i = len(source)
			}
		default:
			out.WriteByte(source[i])
			i++
		}
	}
	return out.String()
}
