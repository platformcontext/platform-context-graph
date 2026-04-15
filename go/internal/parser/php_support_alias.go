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
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
) string {
	if matches := phpTypedVariablePattern.FindStringSubmatch(rawLine); len(matches) == 2 && strings.Contains(rawLine, variable) {
		return normalizePHPTypeName(matches[1])
	}
	if matches := phpVariableTypePattern.FindStringSubmatch(rawLine); len(matches) == 2 {
		return normalizePHPTypeName(matches[1])
	}
	if matches := phpAssignmentPattern.FindStringSubmatch(rawLine); len(matches) == 3 && matches[1] == variable {
		if inferred := inferPHPReferenceType(matches[2], classContext, classPropertyTypes, localVariableTypes); inferred != "" {
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
) string {
	return inferPHPReferenceType(raw, classContext, classPropertyTypes, localVariableTypes)
}

func inferPHPReferenceType(
	raw string,
	classContext string,
	classPropertyTypes map[string]map[string]string,
	localVariableTypes map[string]string,
) string {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}

	if matches := phpNewCallPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
		return normalizePHPTypeName(matches[1])
	}

	if strings.HasPrefix(trimmed, "$this->") && classContext != "" {
		propertyChain := strings.TrimPrefix(trimmed, "$this->")
		if propertyChain == "" {
			return ""
		}
		propertyName := propertyChain
		if index := strings.Index(propertyChain, "->"); index >= 0 {
			propertyName = propertyChain[:index]
		}
		propertyName = strings.TrimSpace(propertyName)
		if propertyName == "" {
			return ""
		}
		return strings.TrimSpace(classPropertyTypes[classContext][propertyName])
	}

	if matches := phpReferenceVariablePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
		if localVariableTypes != nil {
			return strings.TrimSpace(localVariableTypes[matches[1]])
		}
	}

	return ""
}
