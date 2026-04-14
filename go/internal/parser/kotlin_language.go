package parser

import (
	"regexp"
	"slices"
	"strings"
)

var (
	kotlinImportPattern      = regexp.MustCompile(`^\s*import\s+([^\s]+)`)
	kotlinClassPattern       = regexp.MustCompile(`^\s*(?:data\s+|sealed\s+|abstract\s+|open\s+)?class\s+([A-Za-z_]\w*)`)
	kotlinObjectPattern      = regexp.MustCompile(`^\s*object\s+([A-Za-z_]\w*)`)
	kotlinCompanionPattern   = regexp.MustCompile(`^\s*companion\s+object(?:\s+([A-Za-z_]\w*))?`)
	kotlinInterfacePattern   = regexp.MustCompile(`^\s*interface\s+([A-Za-z_]\w*)`)
	kotlinEnumPattern        = regexp.MustCompile(`^\s*enum\s+class\s+([A-Za-z_]\w*)`)
	kotlinFunctionPattern    = regexp.MustCompile(`\bfun\s+(?:<[^>]+>\s*)?(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)\s*\(`)
	kotlinConstructorPattern = regexp.MustCompile(`^\s*(?:(?:public|private|protected|internal)\s+)?constructor\s*\(`)
	kotlinVariablePattern    = regexp.MustCompile(`^\s*(?:private|public|protected|internal)?\s*(?:const\s+)?(?:val|var)\s+([A-Za-z_]\w*)`)
	kotlinCallPattern        = regexp.MustCompile(`\b([A-Za-z_]\w*)\s*\(`)
)

func (e *Engine) parseKotlin(path string, isDependency bool, options Options) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	payload := basePayload(path, "kotlin", isDependency)
	payload["interfaces"] = []map[string]any{}

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

		if matches := kotlinImportPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			appendBucket(payload, "imports", map[string]any{
				"name":        strings.TrimSpace(matches[1]),
				"line_number": lineNumber,
				"lang":        "kotlin",
			})
		}

		if matches := kotlinClassPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "kotlin",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinObjectPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "kotlin",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinCompanionPattern.FindStringSubmatch(trimmed); len(matches) >= 1 {
			name := "Companion"
			if len(matches) == 2 && strings.TrimSpace(matches[1]) != "" {
				name = matches[1]
			}
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "kotlin",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinInterfacePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "interfaces", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "kotlin",
			})
			stack = append(stack, scopedContext{kind: "interface", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinEnumPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			appendBucket(payload, "classes", map[string]any{
				"name":        name,
				"line_number": lineNumber,
				"end_line":    lineNumber,
				"lang":        "kotlin",
			})
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}

		if matches := kotlinFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 3 {
			name := matches[2]
			if strings.TrimSpace(name) != "" {
				item := map[string]any{
					"name":        name,
					"line_number": lineNumber,
					"end_line":    lineNumber,
					"lang":        "kotlin",
					"decorators":  []string{},
				}
				if classContext := currentScopedName(stack, "class"); classContext != "" {
					item["class_context"] = classContext
				}
				if options.IndexSource {
					item["source"] = rawLine
				}
				appendBucket(payload, "functions", item)
			}
		}
		if kotlinConstructorPattern.MatchString(trimmed) {
			item := map[string]any{
				"name":             "constructor",
				"line_number":      lineNumber,
				"end_line":         lineNumber,
				"constructor_kind": "secondary",
				"lang":             "kotlin",
				"decorators":       []string{},
			}
			if classContext := currentScopedName(stack, "class"); classContext != "" {
				item["class_context"] = classContext
			}
			if options.IndexSource {
				item["source"] = rawLine
			}
			appendBucket(payload, "functions", item)
		}

		if matches := kotlinVariablePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			if _, ok := seenVariables[name]; !ok {
				seenVariables[name] = struct{}{}
				appendBucket(payload, "variables", map[string]any{
					"name":        name,
					"line_number": lineNumber,
					"end_line":    lineNumber,
					"lang":        "kotlin",
				})
			}
		}

		for _, match := range kotlinCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			name := match[1]
			switch name {
			case "fun", "if", "for", "while", "when", "return", "class", "interface":
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
				"lang":        "kotlin",
			})
		}

		braceDepth += braceDelta(rawLine)
		stack = popCompletedScopes(stack, braceDepth)
	}

	sortNamedBucket(payload, "functions")
	sortNamedBucket(payload, "classes")
	sortNamedBucket(payload, "interfaces")
	sortNamedBucket(payload, "variables")
	sortNamedBucket(payload, "imports")
	sortNamedBucket(payload, "function_calls")

	return payload, nil
}

func (e *Engine) preScanKotlin(path string) ([]string, error) {
	payload, err := e.parseKotlin(path, false, Options{})
	if err != nil {
		return nil, err
	}
	names := collectBucketNames(payload, "functions", "classes", "interfaces")
	slices.Sort(names)
	return names, nil
}
