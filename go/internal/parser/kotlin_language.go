package parser

import (
	"regexp"
	"slices"
	"strconv"
	"strings"
)

var (
	kotlinImportPattern        = regexp.MustCompile(`^\s*import\s+([^\s]+)(?:\s+as\s+([A-Za-z_]\w*))?`)
	kotlinClassPattern         = regexp.MustCompile(`^\s*(?:data\s+|sealed\s+|abstract\s+|open\s+)?class\s+([A-Za-z_]\w*)`)
	kotlinObjectPattern        = regexp.MustCompile(`^\s*object\s+([A-Za-z_]\w*)`)
	kotlinCompanionPattern     = regexp.MustCompile(`^\s*companion\s+object(?:\s+([A-Za-z_]\w*))?`)
	kotlinInterfacePattern     = regexp.MustCompile(`^\s*interface\s+([A-Za-z_]\w*)`)
	kotlinEnumPattern          = regexp.MustCompile(`^\s*enum\s+class\s+([A-Za-z_]\w*)`)
	kotlinFunctionPattern      = regexp.MustCompile(`\bfun\s+(?:<[^>]+>\s*)?(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)\s*\(`)
	kotlinConstructorPattern   = regexp.MustCompile(`^\s*(?:(?:public|private|protected|internal)\s+)?constructor\s*\(`)
	kotlinVariablePattern      = regexp.MustCompile(`^\s*(?:private|public|protected|internal)?\s*(?:const\s+)?(?:val|var)\s+([A-Za-z_]\w*)`)
	kotlinTypedVariablePattern = regexp.MustCompile(`^\s*(?:private|public|protected|internal)?\s*(?:const\s+)?(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`)
	kotlinCtorAssignPattern    = regexp.MustCompile(`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*([A-Za-z_]\w*)\s*\(`)
	kotlinStringAssignPattern  = regexp.MustCompile(`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*"([^"]*)"`)
	kotlinAliasAssignPattern   = regexp.MustCompile(`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*((?:this\.)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*$`)
	kotlinThisCallPattern      = regexp.MustCompile(`this\.([A-Za-z_]\w*)\s*\(`)
	kotlinCallPattern          = regexp.MustCompile(`\b((?:[A-Za-z_]\w*\.)*)([A-Za-z_]\w*)\s*\(`)
	kotlinInfixCallPattern     = regexp.MustCompile(`^(?:return\s+)?([A-Za-z_]\w*)\s+([A-Za-z_]\w*)\s+(.+)$`)
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
	localVariableTypes := make(map[string]map[string]string)
	classPropertyTypes := make(map[string]map[string]string)
	functionReturnTypes := make(map[string]string)

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
			if properties := kotlinPrimaryConstructorPropertyTypes(rawLine); len(properties) > 0 {
				if _, ok := classPropertyTypes[name]; !ok {
					classPropertyTypes[name] = make(map[string]string, len(properties))
				}
				for propertyName, propertyType := range properties {
					classPropertyTypes[name][propertyName] = propertyType
				}
			}
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
				if receiverType := strings.TrimSpace(matches[1]); receiverType != "" {
					item["extension_receiver"] = receiverType
					if _, ok := item["class_context"]; !ok {
						item["class_context"] = receiverType
					}
				}
				if options.IndexSource {
					item["source"] = rawLine
				}
				appendBucket(payload, "functions", item)
				if receiverType, functionName, returnType := kotlinFunctionDeclarationReturnType(trimmed); functionName != "" && returnType != "" {
					key := functionName
					if receiverType != "" {
						key = receiverType + "." + functionName
					} else if classContext := currentScopedName(stack, "class"); classContext != "" {
						key = classContext + "." + functionName
					}
					functionReturnTypes[key] = returnType
				}
				if strings.Contains(rawLine, "{") {
					stack = append(stack, scopedContext{
						kind:       "function",
						name:       name,
						braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")),
					})
				}
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
			functionContext := currentScopedName(stack, "function")
			classContext := currentScopedName(stack, "class")
			if typedType := kotlinTypedDeclarationType(trimmed); typedType != "" {
				switch {
				case functionContext != "":
					if _, ok := localVariableTypes[functionContext]; !ok {
						localVariableTypes[functionContext] = make(map[string]string)
					}
					localVariableTypes[functionContext][name] = typedType
				case classContext != "":
					if _, ok := classPropertyTypes[classContext]; !ok {
						classPropertyTypes[classContext] = make(map[string]string)
					}
					classPropertyTypes[classContext][name] = typedType
				}
			} else if functionContext != "" {
				if _, ok := localVariableTypes[functionContext]; !ok {
					localVariableTypes[functionContext] = make(map[string]string)
				}
				if inferredType := kotlinInferAssignedVariableType(
					trimmed,
					name,
					functionContext,
					classContext,
					localVariableTypes,
					classPropertyTypes,
					functionReturnTypes,
				); inferredType != "" {
					localVariableTypes[functionContext][name] = inferredType
				}
			}
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
		if matches := kotlinInfixCallPattern.FindStringSubmatch(trimmed); len(matches) == 4 {
			receiver := matches[1]
			name := matches[2]
			if kotlinCallNameAllowed(name) {
				if functionContext := currentScopedName(stack, "function"); functionContext != "" {
					var (
						inferredType string
						classContext string
					)
					if receiver == "this" {
						if currentClass := currentScopedName(stack, "class"); currentClass != "" {
							classContext = currentClass
							inferredType = currentClass
						}
					} else {
						inferredType = kotlinInferReceiverType(
							receiver,
							localVariableTypes[functionContext],
							classPropertyTypes,
							currentScopedName(stack, "class"),
						)
					}
					if inferredType != "" {
						fullName := strings.TrimSpace(receiver + " " + name)
						callKey := fullName + "#" + strconv.Itoa(lineNumber)
						if _, ok := seenLineCalls[callKey]; !ok {
							seenLineCalls[callKey] = struct{}{}
							item := map[string]any{
								"name":              name,
								"full_name":         fullName,
								"line_number":       lineNumber,
								"lang":              "kotlin",
								"inferred_obj_type": inferredType,
							}
							if classContext != "" {
								item["class_context"] = classContext
							}
							appendBucket(payload, "function_calls", item)
						}
					}
				}
			}
		}
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

		normalizedTrimmed := strings.ReplaceAll(trimmed, "?.", ".")
		for _, match := range kotlinCallPattern.FindAllStringSubmatchIndex(normalizedTrimmed, -1) {
			if len(match) != 6 {
				continue
			}
			if functionDeclCutoff >= 0 && match[0] < functionDeclCutoff {
				continue
			}
			receiver := strings.TrimSuffix(strings.TrimSpace(normalizedTrimmed[match[2]:match[3]]), ".")
			name := normalizedTrimmed[match[4]:match[5]]
			if !kotlinCallNameAllowed(name) {
				continue
			}
			if receiver == "" {
				if _, declared := declaredTypeNames[name]; declared {
					continue
				}
			}
			fullName := strings.TrimSpace(normalizedTrimmed[match[2]:match[3]] + normalizedTrimmed[match[4]:match[5]])
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
			} else if receiver != "" {
				if functionContext := currentScopedName(stack, "function"); functionContext != "" {
					if inferredType := kotlinInferReceiverType(
						receiver,
						localVariableTypes[functionContext],
						classPropertyTypes,
						currentScopedName(stack, "class"),
					); inferredType != "" {
						item["inferred_obj_type"] = inferredType
					}
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

func kotlinTypedDeclarationType(line string) string {
	matches := kotlinTypedVariablePattern.FindStringSubmatch(line)
	if len(matches) != 3 {
		return ""
	}
	return strings.TrimSpace(matches[2])
}

func kotlinInferReceiverType(
	receiver string,
	variableTypes map[string]string,
	classPropertyTypes map[string]map[string]string,
	currentClass string,
) string {
	receiver = strings.TrimSpace(receiver)
	if receiver == "" {
		return ""
	}
	receiver = strings.TrimPrefix(receiver, "this.")
	parts := strings.Split(receiver, ".")
	if len(parts) == 0 {
		return ""
	}

	currentType := ""
	root := strings.TrimSpace(parts[0])
	if inferredType := strings.TrimSpace(variableTypes[root]); inferredType != "" {
		currentType = inferredType
	} else if currentClass != "" {
		currentType = strings.TrimSpace(classPropertyTypes[currentClass][root])
	}
	if currentType == "" {
		return ""
	}
	if len(parts) == 1 {
		return currentType
	}

	for _, segment := range parts[1:] {
		name := strings.TrimSpace(segment)
		if name == "" {
			return ""
		}
		properties := classPropertyTypes[currentType]
		if len(properties) == 0 {
			return ""
		}
		nextType := strings.TrimSpace(properties[name])
		if nextType == "" {
			return ""
		}
		currentType = nextType
	}
	return currentType
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

func kotlinCallNameAllowed(name string) bool {
	switch name {
	case "fun", "if", "for", "while", "when", "return", "class", "interface":
		return false
	default:
		return true
	}
}
