package reducer

import (
	"path/filepath"
	"strings"

	"github.com/platformcontext/platform-context-graph/go/internal/facts"
)

func collectCodeCallRepositoryImports(
	envelopes []facts.Envelope,
) map[string]map[string][]string {
	repositoryImports := make(map[string]map[string][]string)
	for _, env := range envelopes {
		if env.FactKind != "repository" {
			continue
		}
		repositoryID := payloadStr(env.Payload, "repo_id")
		if repositoryID == "" {
			repositoryID = payloadStr(env.Payload, "graph_id")
		}
		if repositoryID == "" {
			continue
		}
		imports, ok := env.Payload["imports_map"]
		if !ok || imports == nil {
			continue
		}
		normalized := codeCallNormalizeRepositoryImports(imports)
		if len(normalized) == 0 {
			continue
		}
		repositoryImports[repositoryID] = normalized
	}
	return repositoryImports
}

func codeCallNormalizeRepositoryImports(value any) map[string][]string {
	result := make(map[string][]string)

	appendPath := func(name string, path string) {
		name = strings.TrimSpace(name)
		path = normalizeCodeCallPath(path)
		if name == "" || path == "" {
			return
		}
		for _, existing := range result[name] {
			if existing == path {
				return
			}
		}
		result[name] = append(result[name], path)
	}

	switch typed := value.(type) {
	case map[string][]string:
		for name, paths := range typed {
			for _, path := range paths {
				appendPath(name, path)
			}
		}
	case map[string]any:
		for name, rawPaths := range typed {
			switch paths := rawPaths.(type) {
			case []string:
				for _, path := range paths {
					appendPath(name, path)
				}
			case []any:
				for _, rawPath := range paths {
					appendPath(name, anyToString(rawPath))
				}
			}
		}
	}

	return result
}

func resolveGenericCallee(
	index codeEntityIndex,
	repositoryID string,
	repositoryImports map[string][]string,
	rawPath string,
	relativePath string,
	fileData map[string]any,
	call map[string]any,
) (string, string) {
	if entityID := resolveSameFileCalleeEntityID(index, rawPath, relativePath, call); entityID != "" {
		return entityID, codeCallPreferredPath(rawPath, relativePath)
	}

	language := codeCallLanguage(call, rawPath, relativePath)
	for _, name := range codeCallExactCandidateNames(call, language) {
		if entityID := index.uniqueNameByRepo[repositoryID][name]; entityID != "" {
			return entityID, index.entityFileByID[entityID]
		}
	}

	return resolveImportedCrossFileCallee(
		index,
		repositoryImports,
		rawPath,
		relativePath,
		fileData,
		call,
	)
}

func resolveImportedCrossFileCallee(
	index codeEntityIndex,
	repositoryImports map[string][]string,
	rawPath string,
	relativePath string,
	fileData map[string]any,
	call map[string]any,
) (string, string) {
	if len(repositoryImports) == 0 {
		return "", ""
	}

	importEntries := mapSlice(fileData["imports"])
	if len(importEntries) == 0 {
		return "", ""
	}

	for _, target := range codeCallImportedTargets(importEntries, call) {
		paths := repositoryImports[target.symbolName]
		if len(paths) == 0 {
			continue
		}
		matchedPath := codeCallMatchImportedPath(rawPath, relativePath, target.importSource, paths)
		if matchedPath == "" {
			continue
		}
		if entityID := index.uniqueNameByPath[matchedPath][target.symbolName]; entityID != "" {
			return entityID, index.entityFileByID[entityID]
		}
	}

	return "", ""
}

type codeCallImportedTarget struct {
	symbolName   string
	importSource string
}

func codeCallImportedTargets(
	importEntries []map[string]any,
	call map[string]any,
) []codeCallImportedTarget {
	callName := strings.TrimSpace(anyToString(call["name"]))
	callFullName := strings.TrimSpace(anyToString(call["full_name"]))
	if callName == "" {
		return nil
	}

	targets := make([]codeCallImportedTarget, 0, 2)
	appendTarget := func(symbolName string, importSource string) {
		symbolName = strings.TrimSpace(symbolName)
		importSource = strings.TrimSpace(importSource)
		if symbolName == "" || importSource == "" {
			return
		}
		for _, existing := range targets {
			if existing.symbolName == symbolName && existing.importSource == importSource {
				return
			}
		}
		targets = append(targets, codeCallImportedTarget{
			symbolName:   symbolName,
			importSource: importSource,
		})
	}

	for _, entry := range importEntries {
		entryName := strings.TrimSpace(anyToString(entry["name"]))
		entryAlias := strings.TrimSpace(anyToString(entry["alias"]))
		entrySource := strings.TrimSpace(anyToString(entry["source"]))
		if entrySource == "" {
			continue
		}

		localName := entryName
		if entryAlias != "" {
			localName = entryAlias
		}
		if localName == callName && entryName != "*" {
			appendTarget(entryName, entrySource)
		}

		if entryName == "*" && entryAlias != "" {
			prefix := entryAlias + "."
			if strings.HasPrefix(callFullName, prefix) {
				appendTarget(callName, entrySource)
			}
		}
	}

	return targets
}

func codeCallMatchImportedPath(
	rawPath string,
	relativePath string,
	importSource string,
	candidatePaths []string,
) string {
	for _, expectedPath := range codeCallRelativeImportCandidates(rawPath, relativePath, importSource) {
		for _, candidatePath := range candidatePaths {
			if normalizeCodeCallPath(candidatePath) == expectedPath {
				return expectedPath
			}
		}
	}
	return ""
}

func codeCallRelativeImportCandidates(
	rawPath string,
	relativePath string,
	importSource string,
) []string {
	importSource = strings.TrimSpace(importSource)
	if !strings.HasPrefix(importSource, ".") {
		return nil
	}

	callerPath := normalizeCodeCallPath(rawPath)
	if callerPath == "" {
		callerPath = normalizeCodeCallPath(relativePath)
	}
	if callerPath == "" {
		return nil
	}

	basePath := normalizeCodeCallPath(filepath.Join(filepath.Dir(callerPath), importSource))
	if basePath == "" {
		return nil
	}

	candidates := make([]string, 0, 10)
	appendCandidate := func(value string) {
		normalized := normalizeCodeCallPath(value)
		if normalized == "" {
			return
		}
		for _, existing := range candidates {
			if existing == normalized {
				return
			}
		}
		candidates = append(candidates, normalized)
	}

	appendCandidate(basePath)
	for _, ext := range []string{".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"} {
		appendCandidate(basePath + ext)
		appendCandidate(filepath.Join(basePath, "index"+ext))
	}

	return candidates
}
