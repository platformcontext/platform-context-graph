package parser

import (
	"regexp"
	"strings"
)

var (
	phpAssignmentPattern        = regexp.MustCompile(`^\s*(\$[A-Za-z_]\w*)\s*=\s*([^;]+)`)
	phpReferenceVariablePattern = regexp.MustCompile(`^\$([A-Za-z_]\w*)`)
)

func currentPHPFunctionScopeKey(stack []phpScopedContext) string {
	contextName, contextKind, _ := currentPHPContext(stack)
	if contextName == "" {
		return ""
	}
	if contextKind != "function_definition" && contextKind != "method_declaration" {
		return ""
	}
	classContext := currentPHPScopedName(stack, "class_declaration", "interface_declaration", "trait_declaration")
	return classContext + "::" + contextName
}

func inferPHPVariableType(
	rawLine string,
	variable string,
	lineNumber int,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	if matches := phpTypedVariablePattern.FindStringSubmatch(rawLine); len(matches) == 2 && strings.Contains(rawLine, variable) {
		return normalizePHPTypeName(matches[1])
	}
	if matches := phpVariableTypePattern.FindStringSubmatch(rawLine); len(matches) == 2 {
		return normalizePHPTypeName(matches[1])
	}
	if matches := phpAssignmentPattern.FindStringSubmatch(rawLine); len(matches) == 3 && matches[1] == variable {
		if strings.Contains(matches[2], "new class") {
			return phpAnonymousClassName(lineNumber)
		}
		if inferred := inferPHPReferenceType(matches[2], classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes); inferred != "" {
			return inferred
		}
		if inferred := inferPHPFunctionCallType(matches[2], functionReturnTypes); inferred != "" {
			return inferred
		}
	}
	return "mixed"
}

func inferPHPMethodReceiverType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	trimmed := normalizePHPParenthesizedReceiverExpression(raw)
	if trimmed == "" {
		return ""
	}
	if index := strings.LastIndex(trimmed, "->"); index >= 0 {
		trimmed = trimmed[:index]
	}
	return inferPHPReferenceType(trimmed, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes)
}

func inferPHPReferenceType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	trimmed := normalizePHPParenthesizedReceiverExpression(raw)
	if trimmed == "" {
		return ""
	}

	if matches := phpNewCallPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
		return normalizePHPTypeName(matches[1])
	}

	if inferred := inferPHPFunctionCallType(trimmed, functionReturnTypes); inferred != "" {
		return inferred
	}

	if inferred := inferPHPMethodCallType(trimmed, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes); inferred != "" {
		return inferred
	}

	if inferred := inferPHPCallChainType(trimmed, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes); inferred != "" {
		return inferred
	}

	segments := strings.Split(trimmed, "->")
	if len(segments) == 0 {
		return ""
	}

	root := strings.TrimSpace(segments[0])
	switch {
	case root == "$this":
		if classContext == "" {
			return ""
		}
		return resolvePHPReferenceChainType(classContext, segments[1:], classPropertyTypes, methodReturnTypes, functionReturnTypes)
	case strings.HasPrefix(root, "$"):
		if matches := phpReferenceVariablePattern.FindStringSubmatch(root); len(matches) == 2 {
			if localVariableTypes == nil {
				return ""
			}
			rootType := strings.TrimSpace(localVariableTypes[matches[1]])
			if rootType == "" {
				return ""
			}
			return resolvePHPReferenceChainType(rootType, segments[1:], classPropertyTypes, methodReturnTypes, functionReturnTypes)
		}
	}

	return ""
}

func inferPHPCallChainType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	trimmed := normalizePHPParenthesizedReceiverExpression(raw)
	if trimmed == "" {
		return ""
	}

	segments := strings.Split(trimmed, "->")
	if len(segments) < 2 {
		return ""
	}

	root := strings.TrimSpace(segments[0])
	if root == "" {
		return ""
	}

	remainder := segments[1:]
	if inferred := inferPHPFunctionCallType(root, functionReturnTypes); inferred != "" {
		return resolvePHPReferenceChainType(inferred, remainder, classPropertyTypes, methodReturnTypes, functionReturnTypes)
	}
	if inferred := inferPHPMethodCallType(root, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes); inferred != "" {
		return resolvePHPReferenceChainType(inferred, remainder, classPropertyTypes, methodReturnTypes, functionReturnTypes)
	}

	return ""
}

func inferPHPMethodCallType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	if len(methodReturnTypes) == 0 {
		return ""
	}

	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || !strings.HasSuffix(trimmed, ")") {
		return ""
	}

	openIndex := strings.LastIndex(trimmed, "(")
	if openIndex < 0 {
		return ""
	}
	callHead := strings.TrimSpace(trimmed[:openIndex])
	if callHead == "" {
		return ""
	}

	separatorIndex := strings.LastIndex(callHead, "->")
	separator := "->"
	if staticIndex := strings.LastIndex(callHead, "::"); staticIndex > separatorIndex {
		separatorIndex = staticIndex
		separator = "::"
	}
	if separatorIndex < 0 {
		return ""
	}

	receiverExpr := strings.TrimSpace(callHead[:separatorIndex])
	methodName := strings.TrimSpace(callHead[separatorIndex+len(separator):])
	if receiverExpr == "" || methodName == "" {
		return ""
	}

	receiverType := resolvePHPReferenceRootType(receiverExpr, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes)
	if receiverType == "" {
		return ""
	}

	return lookupPHPMethodReturnType(receiverType, methodName, methodReturnTypes)
}

func resolvePHPReferenceRootType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}

	if trimmed == "self" || trimmed == "static" {
		return classContext
	}

	if inferred := inferPHPReferenceType(trimmed, classContext, classPropertyTypes, localVariableTypes, methodReturnTypes, functionReturnTypes); inferred != "" {
		return inferred
	}

	if strings.HasPrefix(trimmed, "$") {
		return ""
	}

	return normalizePHPTypeName(trimmed)
}

func inferPHPFunctionCallType(
	raw string,
	functionReturnTypes map[string]string,
) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" || !strings.HasSuffix(trimmed, ")") {
		return ""
	}

	openIndex := strings.LastIndex(trimmed, "(")
	if openIndex < 0 {
		return ""
	}

	callName := strings.TrimSpace(trimmed[:openIndex])
	if callName == "" || strings.Contains(callName, "->") || strings.Contains(callName, "::") {
		return ""
	}

	return lookupPHPFunctionReturnType(callName, functionReturnTypes)
}

func lookupPHPFunctionReturnType(
	functionName string,
	functionReturnTypes map[string]string,
) string {
	if functionName == "" {
		return ""
	}

	normalizedFunctionName := normalizePHPTypeName(functionName)
	if normalizedFunctionName == "" {
		return ""
	}

	for _, candidateFunctionName := range []string{functionName, normalizedFunctionName} {
		if returns := normalizePHPTypeName(functionReturnTypes[strings.TrimSpace(candidateFunctionName)]); returns != "" {
			switch returns {
			case "self", "static":
				return normalizedFunctionName
			case "parent":
				return ""
			default:
				return returns
			}
		}
	}

	return ""
}

func lookupPHPMethodReturnType(
	className string,
	methodName string,
	methodReturnTypes map[string]map[string]string,
) string {
	if className == "" || methodName == "" {
		return ""
	}

	normalizedClassName := normalizePHPTypeName(className)
	if normalizedClassName == "" {
		return ""
	}

	for _, candidateClassName := range []string{className, normalizedClassName} {
		if strings.TrimSpace(candidateClassName) == "" {
			continue
		}
		if returns := normalizePHPTypeName(methodReturnTypes[strings.TrimSpace(candidateClassName)][methodName]); returns != "" {
			switch returns {
			case "self", "static":
				return normalizedClassName
			case "parent":
				return ""
			default:
				return returns
			}
		}
	}

	return ""
}

func extractPHPReturnType(lines []string, startIndex int, rawLine string) string {
	signature := collectPHPFunctionSignature(lines, startIndex, rawLine)
	matches := phpFunctionReturnPattern.FindStringSubmatch(signature)
	if len(matches) != 2 {
		return ""
	}
	return normalizePHPTypeName(matches[1])
}

func collectPHPFunctionSignature(lines []string, startIndex int, rawLine string) string {
	signature := strings.TrimSpace(rawLine)
	if signature == "" {
		return ""
	}
	if strings.Contains(signature, "{") || strings.Contains(signature, ";") {
		return signature
	}

	for index := startIndex + 1; index < len(lines); index++ {
		nextLine := strings.TrimSpace(lines[index])
		if nextLine == "" {
			continue
		}
		signature += " " + nextLine
		if strings.Contains(nextLine, "{") || strings.Contains(nextLine, ";") {
			break
		}
	}

	return signature
}

func resolvePHPReferenceChainType(
	rootType string,
	segments []string,
	classPropertyTypes map[string]map[string]string,
	methodReturnTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
	currentType := strings.TrimSpace(rootType)
	if currentType == "" {
		return ""
	}
	for _, segment := range segments {
		segmentName := strings.TrimSpace(segment)
		if segmentName == "" {
			return ""
		}
		if strings.HasSuffix(segmentName, ")") {
			openIndex := strings.Index(segmentName, "(")
			if openIndex < 0 {
				return ""
			}
			methodName := strings.TrimSpace(segmentName[:openIndex])
			if methodName == "" {
				return ""
			}
			nextType := lookupPHPMethodReturnType(currentType, methodName, methodReturnTypes)
			if nextType == "" {
				return ""
			}
			currentType = nextType
			continue
		}
		nextType := normalizePHPTypeName(classPropertyTypes[currentType][segmentName])
		if nextType == "" {
			return ""
		}
		currentType = nextType
	}
	return currentType
}

func normalizePHPParenthesizedReceiverExpression(raw string) string {
	trimmed := strings.TrimSpace(raw)
	for trimmed != "" && strings.HasPrefix(trimmed, "(") {
		closeIndex := findPHPMatchingParen(trimmed)
		if closeIndex < 0 {
			return trimmed
		}
		remainder := strings.TrimSpace(trimmed[closeIndex+1:])
		if remainder != "" && !strings.HasPrefix(remainder, "->") && !strings.HasPrefix(remainder, "::") {
			return trimmed
		}
		trimmed = strings.TrimSpace(trimmed[1:closeIndex]) + remainder
	}
	return trimmed
}

func findPHPMatchingParen(raw string) int {
	depth := 0
	for index, r := range raw {
		switch r {
		case '(':
			depth++
		case ')':
			depth--
			if depth == 0 {
				return index
			}
			if depth < 0 {
				return -1
			}
		}
	}
	return -1
}
