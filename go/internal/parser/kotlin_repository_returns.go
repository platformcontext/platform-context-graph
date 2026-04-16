package parser

import (
	"io/fs"
	"path/filepath"
	"strings"
)

func kotlinCollectSiblingFunctionReturnTypes(currentPath string) (map[string]string, error) {
	root := filepath.Dir(currentPath)
	currentAbs, err := filepath.Abs(currentPath)
	if err != nil {
		return nil, err
	}

	candidates := make(map[string]struct {
		value     string
		ambiguous bool
	})
	record := func(key string, returnType string) {
		key = strings.TrimSpace(key)
		returnType = strings.TrimSpace(returnType)
		if key == "" || returnType == "" {
			return
		}
		candidate, ok := candidates[key]
		if !ok {
			candidates[key] = struct {
				value     string
				ambiguous bool
			}{value: returnType}
			return
		}
		if candidate.value == returnType {
			return
		}
		candidate.ambiguous = true
		candidates[key] = candidate
	}

	walkErr := filepath.WalkDir(root, func(path string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if entry.IsDir() || filepath.Ext(path) != ".kt" {
			return nil
		}
		if absPath, err := filepath.Abs(path); err == nil && absPath == currentAbs {
			return nil
		}

		functionReturnTypes, err := kotlinCollectFunctionReturnTypesFromFile(path)
		if err != nil {
			return err
		}
		for key, returnType := range functionReturnTypes {
			record(key, returnType)
		}
		return nil
	})
	if walkErr != nil {
		return nil, walkErr
	}

	results := make(map[string]string, len(candidates))
	for key, candidate := range candidates {
		if candidate.ambiguous || candidate.value == "" {
			continue
		}
		results[key] = candidate.value
	}
	return results, nil
}

func kotlinCollectFunctionReturnTypesFromFile(path string) (map[string]string, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	lines := strings.Split(string(source), "\n")
	braceDepth := 0
	stack := make([]scopedContext, 0)
	results := make(map[string]string)

	for _, rawLine := range lines {
		trimmed := strings.TrimSpace(rawLine)
		if trimmed == "" || strings.HasPrefix(trimmed, "//") {
			braceDepth += braceDelta(rawLine)
			stack = popCompletedScopes(stack, braceDepth)
			continue
		}

		if matches := kotlinClassPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			stack = append(stack, scopedContext{kind: "class", name: matches[1], braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinObjectPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			stack = append(stack, scopedContext{kind: "class", name: matches[1], braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinCompanionPattern.FindStringSubmatch(trimmed); len(matches) >= 1 {
			name := "Companion"
			if len(matches) == 2 && strings.TrimSpace(matches[1]) != "" {
				name = matches[1]
			}
			stack = append(stack, scopedContext{kind: "class", name: name, braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinInterfacePattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			stack = append(stack, scopedContext{kind: "class", name: matches[1], braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}
		if matches := kotlinEnumPattern.FindStringSubmatch(trimmed); len(matches) == 2 {
			stack = append(stack, scopedContext{kind: "class", name: matches[1], braceDepth: braceDepth + max(1, strings.Count(rawLine, "{"))})
		}

		if matches := kotlinFunctionPattern.FindStringSubmatch(trimmed); len(matches) == 3 {
			receiverType, functionName, returnType := kotlinFunctionDeclarationReturnType(trimmed)
			if functionName != "" && returnType != "" {
				key := functionName
				if receiverType != "" {
					key = receiverType + "." + functionName
				} else if classContext := currentScopedName(stack, "class"); classContext != "" {
					key = classContext + "." + functionName
				}
				results[key] = returnType
			}
			if strings.Contains(rawLine, "{") {
				stack = append(stack, scopedContext{
					kind:       "function",
					name:       matches[2],
					braceDepth: braceDepth + max(1, strings.Count(rawLine, "{")),
				})
			}
		}

		braceDepth += braceDelta(rawLine)
		stack = popCompletedScopes(stack, braceDepth)
	}

	return results, nil
}
