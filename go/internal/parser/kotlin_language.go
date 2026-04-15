package parser

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
)

var (
	kotlinImportPattern      = regexp.MustCompile(`^\s*import\s+([^\s]+)(?:\s+as\s+([A-Za-z_]\w*))?`)
	kotlinClassPattern       = regexp.MustCompile(`^\s*(?:data\s+|sealed\s+|abstract\s+|open\s+)?class\s+([A-Za-z_]\w*)`)
	kotlinObjectPattern      = regexp.MustCompile(`^\s*object\s+([A-Za-z_]\w*)`)
	kotlinCompanionPattern   = regexp.MustCompile(`^\s*companion\s+object(?:\s+([A-Za-z_]\w*))?`)
	kotlinInterfacePattern   = regexp.MustCompile(`^\s*interface\s+([A-Za-z_]\w*)`)
	kotlinEnumPattern        = regexp.MustCompile(`^\s*enum\s+class\s+([A-Za-z_]\w*)`)
	kotlinFunctionPattern    = regexp.MustCompile(`\bfun\s+(?:<[^>]+>\s*)?(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)\s*\(`)
	kotlinConstructorPattern = regexp.MustCompile(`^\s*(?:(?:public|private|protected|internal)\s+)?constructor\s*\(`)
	kotlinVariablePattern    = regexp.MustCompile(`^\s*(?:private|public|protected|internal)?\s*(?:const\s+)?(?:val|var)\s+([A-Za-z_]\w*)`)
	kotlinThisCallPattern    = regexp.MustCompile(`this\.([A-Za-z_]\w*)\s*\(`)
	kotlinCallPattern        = regexp.MustCompile(`\b((?:[A-Za-z_]\w*\.)*)([A-Za-z_]\w*)\s*\(`)
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

	for index, rawLine := range lines {
		lineNumber := index + 1
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "//") {
			braceDepth += braceDelta(rawLine)
			stack = popCompletedScopes(stack, braceDepth)
			continue
		}

		if matches := kotlinImportPattern.FindStringSubmatch(trimmed); len(matches) >= 2 {
			importedName := strings.TrimSpace(matches[1])
			if importedName == "" {
				braceDepth += braceDelta(rawLine)
				stack = popCompletedScopes(stack, braceDepth)
				continue
			}
			alias := kotlinImportAlias(importedName)
			importType := "import"
			if len(matches) == 3 && strings.TrimSpace(matches[2]) != "" {
				alias = strings.TrimSpace(matches[2])
				importType = "alias"
			}
			appendBucket(payload, "imports", map[string]any{
				"name":             importedName,
				"source":           importedName,
				"alias":            alias,
				"full_import_name": strings.TrimSpace(rawLine),
				"import_type":      importType,
				"line_number":      lineNumber,
				"lang":             "kotlin",
			})
		}

		declaredTypeNames := make(map[string]struct{})
		if matches := kotlinClassPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			name := matches[1]
			declaredTypeNames[name] = struct{}{}
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
			declaredTypeNames[name] = struct{}{}
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
			declaredTypeNames[name] = struct{}{}
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
			declaredTypeNames[name] = struct{}{}
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
			declaredTypeNames[name] = struct{}{}
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

		functionDeclCutoff := -1
		if kotlinFunctionPattern.MatchString(trimmed) {
			if idx := strings.Index(trimmed, "="); idx >= 0 {
				functionDeclCutoff = idx
			}
			if idx := strings.Index(trimmed, "{"); idx >= 0 && (functionDeclCutoff < 0 || idx < functionDeclCutoff) {
				functionDeclCutoff = idx
			}
		}

		seenLineCalls := make(map[string]struct{})
		for _, match := range kotlinThisCallPattern.FindAllStringSubmatch(trimmed, -1) {
			if len(match) != 2 {
				continue
			}
			name := match[1]
			fullName := "this." + name
			callKey := fullName + "#" + strconv.Itoa(lineNumber)
			if _, ok := seenLineCalls[callKey]; ok {
				continue
			}
			seenLineCalls[callKey] = struct{}{}
			item := map[string]any{
				"name":        name,
				"full_name":   fullName,
				"line_number": lineNumber,
				"lang":        "kotlin",
			}
			if classContext := currentScopedName(stack, "class"); classContext != "" {
				item["class_context"] = classContext
			}
			appendBucket(payload, "function_calls", item)
		}

		for _, match := range kotlinCallPattern.FindAllStringSubmatchIndex(trimmed, -1) {
			if len(match) != 6 {
				continue
			}
			if functionDeclCutoff >= 0 && match[0] < functionDeclCutoff {
				continue
			}
			receiver := strings.TrimSuffix(strings.TrimSpace(trimmed[match[2]:match[3]]), ".")
			name := trimmed[match[4]:match[5]]
			switch name {
			case "fun", "if", "for", "while", "when", "return", "class", "interface":
				continue
			}
			if receiver == "" {
				if _, declared := declaredTypeNames[name]; declared {
					continue
				}
			}
			fullName := strings.TrimSpace(trimmed[match[2]:match[3]] + trimmed[match[4]:match[5]])
			callKey := fullName + "#" + strconv.Itoa(lineNumber)
			if _, ok := seenLineCalls[callKey]; ok {
				continue
			}
			seenLineCalls[callKey] = struct{}{}
			item := map[string]any{
				"name":        name,
				"full_name":   fullName,
				"line_number": lineNumber,
				"lang":        "kotlin",
			}
			if receiver == "this" {
				if classContext := currentScopedName(stack, "class"); classContext != "" {
					item["class_context"] = classContext
				}
			}
			appendBucket(payload, "function_calls", item)
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

func kotlinImportAlias(name string) string {
	trimmed := strings.TrimSpace(name)
	if trimmed == "" {
		return ""
	}
	if idx := strings.LastIndex(trimmed, "."); idx >= 0 {
		return strings.TrimSpace(trimmed[idx+1:])
	}
	return trimmed
}
