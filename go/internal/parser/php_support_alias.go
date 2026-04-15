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
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return ""
	}
	if index := strings.LastIndex(trimmed, "->"); index >= 0 {
		trimmed = trimmed[:index]
	}
	return inferPHPReferenceType(trimmed, classContext, classPropertyTypes, localVariableTypes)
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
		return resolvePHPPropertyChainType(classContext, segments[1:], classPropertyTypes)
	case strings.HasPrefix(root, "$"):
		if matches := phpReferenceVariablePattern.FindStringSubmatch(root); len(matches) == 2 {
			if localVariableTypes == nil {
				return ""
			}
			rootType := strings.TrimSpace(localVariableTypes[matches[1]])
			if rootType == "" {
				return ""
			}
			return resolvePHPPropertyChainType(rootType, segments[1:], classPropertyTypes)
		}
	}

	return ""
}

func resolvePHPPropertyChainType(
	rootType string,
	segments []string,
	classPropertyTypes map[string]map[string]string,
) string {
	currentType := strings.TrimSpace(rootType)
	if currentType == "" {
		return ""
	}
	for _, segment := range segments {
		propertyName := strings.TrimSpace(segment)
		if propertyName == "" {
			return ""
		}
		nextType := normalizePHPTypeName(classPropertyTypes[currentType][propertyName])
		if nextType == "" {
			return ""
		}
		currentType = nextType
	}
	return currentType
}
