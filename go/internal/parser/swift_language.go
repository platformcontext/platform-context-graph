package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	swiftImportPattern   = regexp.MustCompile(`^\s*import\s+([A-Za-z0-9_\.]+)`)
	swiftClassPattern    = regexp.MustCompile(`^\s*(?:final\s+)?class\s+([A-Za-z_]\w*)`)
	swiftActorPattern    = regexp.MustCompile(`^\s*actor\s+([A-Za-z_]\w*)`)
	swiftStructPattern   = regexp.MustCompile(`^\s*struct\s+([A-Za-z_]\w*)`)
	swiftEnumPattern     = regexp.MustCompile(`^\s*enum\s+([A-Za-z_]\w*)`)
	swiftFunctionPattern = regexp.MustCompile(`\bfunc\s+([A-Za-z_]\w*)(?:<[^>]+>)?\s*\(`)
	swiftVariablePattern = regexp.MustCompile(`^\s*(?:let|var)\s+([A-Za-z_]\w*)`)
	swiftCallPattern     = regexp.MustCompile(`\b([A-Za-z_]\w*)\s*\(`)
)

func (e *Engine) parseSwift(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "swift", isDependency)
	payload["structs"] = []map[string]any{}
	payload["enums"] = []map[string]any{}

	lines := strings.Split(string(source), "\n")
	braceDepth := 0
	stack := make([]scopedContext, 0)
	seenVariables := make(map[string]struct{})
	seenCalls := make(map[string]struct{})

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "//") {
			braceDepth += braceDelta(rawLine)
			stack = popCompletedScopes(stack, braceDepth)
			continue
		}

		if matches := swiftImportPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			appendBucket(payload, "imports", map[string]any{
				"name":        matches[1],
				"line_number": lineNumber,
				"lang":        "swift",
			})
		}
		if matches := swiftClassPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "swift",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := swiftActorPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "swift",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := swiftStructPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "structs", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "swift",
			})
			stack = append(stack, scopedContext{kind: "struct", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := swiftEnumPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "enums", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "swift",
			})
			stack = append(stack, scopedContext{kind: "enum", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}

		if matches := swiftFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			appendSwiftFunction(payload, matches[1], rawLine, lineNumber, options, currentScopedName(stack, "class", "struct", "enum"))
		}
		if strings.HasPrefix(trimmed, "init(") || strings.Contains(trimmed, " init(") {
			appendSwiftFunction(payload, "init", rawLine, lineNumber, options, currentScopedName(stack, "class", "struct"))
		}

		if matches := swiftVariablePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			if _, ok := seenVariables[name]; !ok {
				seenVariables[name] = struct{}{}
				appendBucket(payload, "variables", map[string]any{
					"name":        name,
					"line_number": lineNumber,
					"end_line":    lineNumber,
					"lang":        "swift",
				})
			}
		}

		for _, match := range swiftCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			name := match[1]
			switch name {
			case "func", "init", "if", "switch", "return":
				continue
			}
			if _, ok := seenCalls[name]; ok {
				continue
			}
			seenCalls[name] = struct{}{}
			appendBucket(payload, "function_calls", map[string]any{
				"name":        name,
				"full_name":   name,
				"line_number": lineNumber,
				"lang":        "swift",
			})
		}

		braceDepth += braceDelta(rawLine)
		stack = popCompletedScopes(stack, braceDepth)
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "structs")
	sortNamedBucket(payload, "enums")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	return payload, nil
}

func (e *Engine) preScanSwift(path string) ([]string, error) {
	payload, err := e.parseSwift(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "structs", "enums")
	slices.Sort(names)
	return names, nil
}

func appendSwiftFunction(
	payload map[string]any,
	name string,
	source string,
	lineNumber int,
	options Options,
	classContext string,
) {
	item := map[string]any{
		"name":        name,
		"line_number": lineNumber,
		"end_line":    lineNumber,
		"lang":        "swift",
		"decorators":  []string{},
	}
	if classContext != "" {
		item["class_context"] = classContext
	}
	if options.IndexSource {
		item["source"] = source
	}
	appendBucket(payload, "functions", item)
}
