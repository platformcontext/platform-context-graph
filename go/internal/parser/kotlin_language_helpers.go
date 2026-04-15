package parser

import (
	"regexp"
	"strings"
)

var kotlinPrimaryConstructorPropertyPattern = regexp.MustCompile(
	`(?m)(?:^|,)\s*(?:(?:@[A-Za-z_]\w*(?:\([^)]*\))?\s+)*)*(?:(?:private|public|protected|internal|override|open|final|const|lateinit)\s+)*(?:val|var)\s+([A-Za-z_]\w*)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`,
)

var (
	kotlinFunctionReturnPattern = regexp.MustCompile(
		`\bfun\s+(?:<[^>]+>\s*)?(?:([A-Za-z_]\w*)\.)?([A-Za-z_]\w*)\s*\([^)]*\)\s*:\s*([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)`,
	)
	kotlinFunctionCallAssignPattern = regexp.MustCompile(
		`^\s*(?:val|var)\s+([A-Za-z_]\w*)\s*=\s*((?:[A-Za-z_]\w*\.)*[A-Za-z_]\w*)\s*\([^)]*\)\s*$`,
	)
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

func kotlinInferAssignedVariableType(
	trimmed string,
	name string,
	functionContext string,
	classContext string,
	localVariableTypes map[string]map[string]string,
	classPropertyTypes map[string]map[string]string,
	functionReturnTypes map[string]string,
) string {
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
	functionReturnTypes map[string]string,
) string {
	callExpression = strings.TrimSpace(callExpression)
	if callExpression == "" {
		return ""
	}

	receiver := ""
	name := callExpression
	if idx := strings.LastIndex(callExpression, "."); idx >= 0 {
		receiver = strings.TrimSpace(callExpression[:idx])
		name = strings.TrimSpace(callExpression[idx+1:])
	}
	if name == "" {
		return ""
	}

	if receiver == "" {
		if currentClass != "" {
			if returnType := strings.TrimSpace(functionReturnTypes[currentClass+"."+name]); returnType != "" {
				return returnType
			}
		}
		return strings.TrimSpace(functionReturnTypes[name])
	}

	inferredReceiverType := kotlinInferReceiverType(receiver, variableTypes, classPropertyTypes, currentClass)
	if inferredReceiverType == "" {
		return ""
	}
	if returnType := strings.TrimSpace(functionReturnTypes[inferredReceiverType+"."+name]); returnType != "" {
		return returnType
	}
	if currentClass != "" {
		if returnType := strings.TrimSpace(functionReturnTypes[currentClass+"."+name]); returnType != "" {
			return returnType
		}
	}
	return strings.TrimSpace(functionReturnTypes[inferredReceiverType+"."+name])
}
