package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	phpNamespacePattern    = regexp.MustCompile(`^\s*namespace\s+([^;]+);`)
	phpUsePattern          = regexp.MustCompile(`^\s*use\s+([^;]+);`)
	phpTypePattern         = regexp.MustCompile(`^\s*(?:abstract\s+|final\s+)?(class|interface|trait)\s+([A-Za-z_]\w*)`)
	phpFunctionPattern     = regexp.MustCompile(`\bfunction\s+([A-Za-z_]\w*)\s*\(`)
	phpVariablePattern     = regexp.MustCompile(`\$[A-Za-z_]\w*`)
	phpMethodCallPattern   = regexp.MustCompile(`(\$[A-Za-z_]\w*(?:->\w+)+)\s*\(`)
	phpNewCallPattern      = regexp.MustCompile(`\bnew\s+([A-Za-z_\\]\w*(?:\\[A-Za-z_]\w*)*)\s*\(`)
	phpFunctionCallPattern = regexp.MustCompile(`\b([A-Za-z_]\w*)\s*\(`)
)

func (e *Engine) parsePHP(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "php", isDependency)
	payload["traits"] = []map[string]any{}
	payload["interfaces"] = []map[string]any{}

	lines := strings.Split(string(source), "\n")
	namespace := ""
	braceDepth := 0
	stack := make([]scopedContext, 0)
	seenVariables := make(map[string]struct{})
	seenCalls := make(map[string]struct{})

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "//") || strings.HasPrefix(trimmed, "#") {
			braceDepth += braceDelta(rawLine)
			stack = popCompletedScopes(stack, braceDepth)
			continue
		}

		if matches := phpNamespacePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			namespace = strings.TrimSpace(matches[1])
		}

		if matches := phpUsePattern.FindStringSubmatch(trimmed); len(matches) == 2 && currentScopedName(stack, "class", "interface", "trait") == "" {
			appendBucket(payload, "imports", map[string]any{
				"name":        strings.TrimSpace(matches[1]),
				"line_number": lineNumber,
				"lang":        "php",
			})
		}

		if matches := phpTypePattern.FindStringSubmatch(trimmed); len(matches) == 3 {
			name := matches[2]
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
			}
			switch matches[1] {
			case "class":
				appendBucket(payload, "classes", item)
				stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
			case "interface":
				appendBucket(payload, "interfaces", item)
				stack = append(stack, scopedContext{kind: "interface", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
			case "trait":
				appendBucket(payload, "traits", item)
				stack = append(stack, scopedContext{kind: "trait", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
			}
		}

		if matches := phpFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			item := map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
				"decorators":  []string{},
			}
			if classContext := currentScopedName(stack, "class", "trait"); classContext != "" {
				item["class_context"] = classContext
			}
			if options.IndexSource {
				item["source"] = rawLine
			}
			appendBucket(payload, "functions", item)
		}

		for _, variable := range phpVariablePattern.FindAllString(rawLine, -1) {
			if variable == "$this" {
				continue
			}
			if _, ok := seenVariables[variable]; ok {
				continue
			}
			seenVariables[variable] = struct{}{}
			appendBucket(payload, "variables", map[string]any{
				"name":        variable,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "php",
			})
		}

		for _, match := range phpMethodCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			fullName := normalizePHPMethodCall(match[1])
			appendUniquePHPCall(payload, seenCalls, fullName, lineNumber)
		}
		for _, match := range phpNewCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			appendUniquePHPCall(payload, seenCalls, lastPathSegment(match[1], `\`), lineNumber)
		}
		for _, match := range phpFunctionCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			name := match[1]
			switch name {
			case "function", "if", "foreach", "for", "switch", "echo", "require_once":
				continue
			}
			appendUniquePHPCall(payload, seenCalls, name, lineNumber)
		}

		braceDepth += braceDelta(rawLine)
		stack = popCompletedScopes(stack, braceDepth)
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "traits")
	sortNamedBucket(payload, "interfaces")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	if namespace != "" {
		payload["namespace"] = namespace
	}

	return payload, nil
}

func (e *Engine) preScanPHP(path string) ([]string, error) {
	payload, err := e.parsePHP(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "traits", "interfaces")
	slices.Sort(names)
	return names, nil
}

func appendUniquePHPCall(
	payload map[string]any,
	seen map[string]struct{},
	fullName string,
	lineNumber int,
) {
	if strings.TrimSpace(fullName) == "" {
		return
	}
	if _, ok := seen[fullName]; ok {
		return
	}
	seen[fullName] = struct{}{}
	appendBucket(payload, "function_calls", map[string]any{
		"name":        fullName,
		"full_name":   fullName,
		"line_number": lineNumber,
		"lang":        "php",
	})
}

func normalizePHPMethodCall(raw string) string {
	parts := strings.Split(raw, "->")
	if len(parts) <= 1 {
		return raw
	}
	return strings.Join(parts[:len(parts)-1], "->") + "." + parts[len(parts)-1]
}
