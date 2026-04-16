package parser

import (
	"regexp"
	"strconv"
	"strings"
)

var kotlinPrimaryConstructorPropertyPattern = regexp.MustCompile(
	`(?m)(?:^|,)\s*(?:(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s+)*)*(?:(?:private|public|protected|internal|override|open|final|const|lateinit)\s+)*(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`,
)

var (
	kotlinFunctionReturnPattern = regexp.MustCompile(
		`\bfun\s+(?:<[^>]+>\s*)?(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)\s*\([^)]*\)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`,
	)
	kotlinSuspendFunctionPattern    = regexp.MustCompile(`\bsuspend\s+fun\b`)
	kotlinFunctionCallAssignPattern = regexp.MustCompile(
		`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*((?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*)\s*\([^()]*\)\s*$`,
	)
	kotlinLazyDelegatedAssignPattern = regexp.MustCompile(
		`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s+by\s+lazy(?:\s*\([^)]*\))?\s*\{\s*(.+?)\s*\}\s*$`,
	)
	kotlinConstructorCallPattern = regexp.MustCompile(`\b([A-Z][A-Za-z_]\w*)\s*\(`)
)

func kotlinPrimaryConstructorPropertyTypes(line string) map[string]string {
	trimmed := strings.TrimSpace(line)
	if trimmed == "" {
		return nil
	}

	openIndex := strings.Index(trimmed, "(")
	if openIndex < 0 {
		return nil
	}
	closeIndex := kotlinMatchingParenIndex(trimmed, openIndex)
	if closeIndex <= openIndex {
		return nil
	}

	constructor := trimmed[openIndex+1 : closeIndex]
	matches := kotlinPrimaryConstructorPropertyPattern.FindAllStringSubmatch(constructor, -1)
	if len(matches) == 0 {
		return nil
	}

	properties := make(map[string]string, len(matches))
	for _, match := range matches {
		if len(match) != 3 {
			continue
		}
		name := strings.TrimSpace(match[1])
		typ := strings.TrimSpace(match[2])
		if name == "" || typ == "" {
			continue
		}
		properties[name] = typ
	}
	if len(properties) == 0 {
		return nil
	}
	return properties
}

func kotlinFunctionDeclarationReturnType(line string) (string, string, string) {
	matches := kotlinFunctionReturnPattern.FindStringSubmatch(strings.TrimSpace(line))
	if len(matches) != 4 {
		return "", "", ""
	}
	return strings.TrimSpace(matches[1]), strings.TrimSpace(matches[2]), strings.TrimSpace(matches[3])
}

func kotlinFunctionIsSuspend(line string) bool {
	return kotlinSuspendFunctionPattern.MatchString(strings.TrimSpace(line))
}

func kotlinCurrentTypeScopeName(stack []scopedContext) string {
	return currentScopedName(stack, "class", "interface")
}

func kotlinTypedDeclarationType(line string) string {
	matches := kotlinTypedVariablePattern.FindStringSubmatch(line)
	if len(matches) != 3 {
		return ""
	}
	return strings.TrimSpace(matches[2])
}

func kotlinInferAssignedVariableType(
	trimmed string,
	name string,
	functionContext string,
	classContext string,
	packageName string,
	localVariableTypes map[string]map[string]string,
	classPropertyTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	trimmed = strings.ReplaceAll(trimmed, "?.", ".")
	trimmed = kotlinStripReceiverPreservingScopeFunctions(trimmed)
	switch {
	case kotlinCtorAssignPattern.MatchString(trimmed):
		assignMatches := kotlinCtorAssignPattern.FindStringSubmatch(trimmed)
		if len(assignMatches) == 3 && assignMatches[1] == name {
			assignedType := strings.TrimSpace(assignMatches[2])
			if assignedType == "" {
				return ""
			}
			if kotlinLooksLikeTypeName(assignedType) {
				return assignedType
			}
			return kotlinInferFunctionCallReturnType(
				assignedType,
				localVariableTypes[functionContext],
				classPropertyTypes,
				classContext,
				packageName,
				functionReturnTypes,
			)
		}
	case kotlinFunctionCallAssignPattern.MatchString(trimmed):
		assignMatches := kotlinFunctionCallAssignPattern.FindStringSubmatch(trimmed)
		if len(assignMatches) == 3 && assignMatches[1] == name {
			return kotlinInferFunctionCallReturnType(
				assignMatches[2],
				localVariableTypes[functionContext],
				classPropertyTypes,
				classContext,
				packageName,
				functionReturnTypes,
			)
		}
	case kotlinStringAssignPattern.MatchString(trimmed):
		assignMatches := kotlinStringAssignPattern.FindStringSubmatch(trimmed)
		if len(assignMatches) == 3 && assignMatches[1] == name {
			return "String"
		}
	case kotlinAliasAssignPattern.MatchString(trimmed):
		assignMatches := kotlinAliasAssignPattern.FindStringSubmatch(trimmed)
		if len(assignMatches) == 3 && assignMatches[1] == name {
			return kotlinInferReceiverType(
				assignMatches[2],
				localVariableTypes[functionContext],
				classPropertyTypes,
				classContext,
				packageName,
				functionReturnTypes,
			)
		}
	case kotlinLazyDelegatedAssignPattern.MatchString(trimmed):
		assignMatches := kotlinLazyDelegatedAssignPattern.FindStringSubmatch(trimmed)
		if len(assignMatches) == 3 && assignMatches[1] == name {
			return kotlinInferReceiverType(
				assignMatches[2],
				localVariableTypes[functionContext],
				classPropertyTypes,
				classContext,
				packageName,
				functionReturnTypes,
			)
		}
	}
	return ""
}

func kotlinMatchingParenIndex(value string, openIndex int) int {
	if openIndex < 0 || openIndex >= len(value) {
		return -1
	}

	depth := 0
	for index, char := range value[openIndex:] {
		switch char {
		case '(':
			depth++
		case ')':
			depth--
			if depth == 0 {
				return openIndex + index
			}
		}
	}

	return -1
}

func kotlinLooksLikeTypeName(name string) bool {
	name = strings.TrimSpace(name)
	if name == "" {
		return false
	}
	first := rune(name[0])
	return first >= 'A' && first <= 'Z'
}

func kotlinInferFunctionCallReturnType(
	callExpression string,
	variableTypes map[string]string,
	classPropertyTypes map[string]map[string]string,
	currentClass string,
	packageName string,
	functionReturnTypes map[string]string,
) string {
	callExpression = strings.TrimSpace(callExpression)
	if callExpression == "" {
		return ""
	}

	if strings.Contains(callExpression, "(") && strings.HasSuffix(callExpression, ")") {
		return kotlinInferMethodCallReturnType(
			callExpression,
			variableTypes,
			classPropertyTypes,
			currentClass,
			packageName,
			functionReturnTypes,
		)
	}

	return kotlinInferMethodCallReturnType(
		callExpression+"()",
		variableTypes,
		classPropertyTypes,
		currentClass,
		packageName,
		functionReturnTypes,
	)
}

func kotlinInferMethodCallReturnType(
	callExpression string,
	variableTypes map[string]string,
	classPropertyTypes map[string]map[string]string,
	currentClass string,
	packageName string,
	functionReturnTypes map[string]string,
) string {
	callExpression = strings.TrimSpace(callExpression)
	if callExpression == "" {
		return ""
	}

	callHead := callExpression
	if idx := strings.LastIndex(callExpression, "("); idx >= 0 && strings.HasSuffix(callExpression, ")") {
		callHead = strings.TrimSpace(callExpression[:idx])
	}
	if callHead == "" {
		return ""
	}

	receiver := ""
	name := callHead
	if idx := strings.LastIndex(callHead, "."); idx >= 0 {
		receiver = strings.TrimSpace(callHead[:idx])
		name = strings.TrimSpace(callHead[idx+1:])
	}
	if name == "" {
		return ""
	}

	if receiver == "" {
		if kotlinLooksLikeTypeName(name) {
			return name
		}
		return kotlinLookupFunctionReturnType(functionReturnTypes, packageName, currentClass, name)
	}

	inferredReceiverType := kotlinInferReceiverType(
		receiver,
		variableTypes,
		classPropertyTypes,
		currentClass,
		packageName,
		functionReturnTypes,
	)
	if inferredReceiverType == "" {
		return ""
	}
	return kotlinLookupFunctionReturnType(functionReturnTypes, packageName, inferredReceiverType, name)
}

func kotlinInferReceiverSegmentType(
	segment string,
	variableTypes map[string]string,
	classPropertyTypes map[string]map[string]string,
	currentClass string,
	packageName string,
	functionReturnTypes map[string]string,
) string {
	segment = strings.TrimSpace(segment)
	if segment == "" {
		return ""
	}

	if strings.Contains(segment, "(") && strings.HasSuffix(segment, ")") {
		return kotlinInferMethodCallReturnType(
			segment,
			variableTypes,
			classPropertyTypes,
			currentClass,
			packageName,
			functionReturnTypes,
		)
	}

	if inferredType := strings.TrimSpace(variableTypes[segment]); inferredType != "" {
		return inferredType
	}
	if currentClass != "" {
		return strings.TrimSpace(classPropertyTypes[currentClass][segment])
	}
	return ""
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

func kotlinAppendConstructorCalls(
	payload map[string]any,
	trimmed string,
	lineNumber int,
	functionDeclCutoff int,
	seenLineCalls map[string]struct{},
	knownTypeNames map[string]struct{},
	skip bool,
) {
	if skip {
		return
	}

	for _, match := range kotlinConstructorCallPattern.FindAllStringSubmatchIndex(trimmed, -1) {
		if len(match) != 4 {
			continue
		}
		if functionDeclCutoff >= 0 && match[0] < functionDeclCutoff {
			continue
		}
		name := trimmed[match[2]:match[3]]
		if _, ok := knownTypeNames[name]; !ok {
			continue
		}
		callKey := name + "#" + strconv.Itoa(lineNumber)
		if _, ok := seenLineCalls[callKey]; ok {
			continue
		}
		seenLineCalls[callKey] = struct{}{}
		appendBucket(payload, "function_calls", map[string]any{
			"name":        name,
			"full_name":   name,
			"line_number": lineNumber,
			"lang":        "kotlin",
		})
	}
}

func kotlinAppendThisCalls(
	payload map[string]any,
	trimmed string,
	lineNumber int,
	seenLineCalls map[string]struct{},
	classContext string,
) {
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
		if classContext != "" {
			item["class_context"] = classContext
		}
		appendBucket(payload, "function_calls", item)
	}
}
