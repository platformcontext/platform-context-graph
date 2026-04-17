package query

import (
	"fmt"
	"path"
	"regexp"
	"sort"
	"strings"

	"gopkg.in/yaml.v3"
)

var (
	terragruntDependencyConfigPathPattern = regexp.MustCompile(`(?i)\bconfig_path\s*=\s*"([^"]+)"`)
	terragruntReadConfigPattern           = regexp.MustCompile(`(?i)read_terragrunt_config\(\s*(?:find_in_parent_folders\(\s*(?:"([^"]+)")?\s*\)|"([^"]+)")`)
	terragruntFindInParentFoldersPattern  = regexp.MustCompile(`(?i)find_in_parent_folders\(\s*(?:"([^"]+)")?\s*\)`)
	terragruntIncludePathPattern          = regexp.MustCompile(`(?i)\bpath\s*=\s*find_in_parent_folders\(\s*(?:"([^"]+)")?\s*\)`)
	localFileFunctionPattern              = regexp.MustCompile(`(?i)\b(?:file|templatefile)\(\s*"([^"]+)"`)
	localVariableFileFunctionPattern      = regexp.MustCompile(`(?i)\b(?:file|templatefile)\(\s*local\.([A-Za-z0-9_]+)`)
	localTerraformModuleSourcePattern     = regexp.MustCompile(`(?is)(?:module\s+"[^"]+"\s*\{[^}]*?|\bterraform\s*\{[^}]*?)\bsource\b\s*=\s*"((?:\./|\.\./|\$\{get_repo_root\(\)\}/)[^"]+)"`)
	localStringAssignmentPattern          = regexp.MustCompile(`(?m)^\s*([A-Za-z0-9_]+)\s*=\s*"([^"]+)"\s*$`)
	localAssignmentStartPattern           = regexp.MustCompile(`^\s*([A-Za-z0-9_]+)\s*=\s*(.+?)\s*$`)
	quotedStringPattern                   = regexp.MustCompile(`"([^"]+)"`)
	ssmConfigPathPattern                  = regexp.MustCompile(`(?i)((?:/(?:configd|api)/[A-Za-z0-9._*/-]+))`)
	ssmParameterARNPattern                = regexp.MustCompile(`(?i):parameter((?:/(?:configd|api)/[A-Za-z0-9._*/-]+))`)
)

func buildRepositoryConfigArtifacts(repoName string, files []FileContent) map[string]any {
	configPaths := make([]map[string]any, 0)
	configPaths = append(configPaths, extractKustomizeConfigPathRows(repoName, files)...)
	configPaths = append(configPaths, extractHCLConfigAssetRows(repoName, files)...)
	configPaths = append(configPaths, extractAnsibleConfigPathRows(repoName, files)...)
	if len(configPaths) == 0 {
		return nil
	}
	sort.Slice(configPaths, func(i, j int) bool {
		leftPath := StringVal(configPaths[i], "path")
		rightPath := StringVal(configPaths[j], "path")
		if leftPath != rightPath {
			return leftPath < rightPath
		}
		leftKind := StringVal(configPaths[i], "evidence_kind")
		rightKind := StringVal(configPaths[j], "evidence_kind")
		if leftKind != rightKind {
			return leftKind < rightKind
		}
		return StringVal(configPaths[i], "relative_path") < StringVal(configPaths[j], "relative_path")
	})
	return map[string]any{"config_paths": configPaths}
}

func isConfigArtifactCandidate(file FileContent) bool {
	relativePath := strings.TrimSpace(file.RelativePath)
	if relativePath == "" {
		return false
	}

	lowerBase := strings.ToLower(path.Base(relativePath))
	switch {
	case lowerBase == "kustomization.yaml", lowerBase == "kustomization.yml", lowerBase == "kustomization":
		return true
	case lowerBase == "terragrunt.hcl":
		return true
	case strings.HasSuffix(lowerBase, ".tfvars"), strings.HasSuffix(lowerBase, ".tfvars.json"):
		return true
	case strings.HasSuffix(lowerBase, ".tf"), strings.HasSuffix(lowerBase, ".hcl"):
		return true
	case strings.HasPrefix(lowerBase, "docker-compose"):
		return false
	case strings.HasSuffix(lowerBase, ".yaml"), strings.HasSuffix(lowerBase, ".yml"), strings.HasSuffix(lowerBase, ".json"):
		return true
	default:
		return false
	}
}

func extractHCLConfigAssetRows(repoName string, files []FileContent) []map[string]any {
	rows := make([]map[string]any, 0)
	seen := map[string]struct{}{}
	for _, file := range files {
		lowerBase := strings.ToLower(path.Base(file.RelativePath))
		if strings.HasSuffix(lowerBase, ".tfvars") || strings.HasSuffix(lowerBase, ".tfvars.json") {
			rows = appendConfigArtifactRow(rows, seen, cleanRepositoryRelativePath(file.RelativePath), repoName, file.RelativePath, "terraform_var_file")
			continue
		}
		if lowerBase != "terragrunt.hcl" && !strings.HasSuffix(lowerBase, ".tf") && !strings.HasSuffix(lowerBase, ".hcl") {
			continue
		}
		localConfigAssignments := extractLocalConfigAssignments(file.Content)
		for _, match := range terragruntDependencyConfigPathPattern.FindAllStringSubmatch(file.Content, -1) {
			if len(match) < 2 {
				continue
			}
			configPath := strings.TrimSpace(match[1])
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "terragrunt_dependency_config_path")
		}
		for _, match := range terragruntReadConfigPattern.FindAllStringSubmatch(file.Content, -1) {
			configPath := normalizeTerragruntParentConfigPath(match)
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "terragrunt_read_config")
		}
		for _, match := range terragruntIncludePathPattern.FindAllStringSubmatch(file.Content, -1) {
			configPath := normalizeTerragruntParentConfigPath(match)
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "terragrunt_include_path")
		}
		for _, match := range terragruntFindInParentFoldersPattern.FindAllStringSubmatch(file.Content, -1) {
			configPath := normalizeTerragruntParentConfigPath(match)
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "terragrunt_find_in_parent_folders")
		}
		for _, match := range localFileFunctionPattern.FindAllStringSubmatch(file.Content, -1) {
			configPath := normalizeLocalConfigAssetPath(match)
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "local_config_asset")
		}
		for _, match := range localVariableFileFunctionPattern.FindAllStringSubmatch(file.Content, -1) {
			if len(match) < 2 {
				continue
			}
			configPath := normalizeLocalConfigAssetPath([]string{"", localConfigAssignments[match[1]]})
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "local_config_asset")
		}
		for _, match := range localTerraformModuleSourcePattern.FindAllStringSubmatch(file.Content, -1) {
			configPath := normalizeLocalConfigAssetPath(match)
			if configPath == "" {
				continue
			}
			rows = appendConfigArtifactRow(rows, seen, configPath, repoName, file.RelativePath, "terraform_module_source_path")
		}
	}
	return rows
}

func extractLocalConfigAssignments(content string) map[string]string {
	assignments := make(map[string]string)
	lines := strings.Split(content, "\n")
	inLocals := false
	depth := 0
	currentName := ""
	currentExpression := strings.Builder{}
	currentParenDepth := 0
	for _, line := range lines {
		trimmed := strings.TrimSpace(line)
		if !inLocals {
			if !strings.HasPrefix(trimmed, "locals") || !strings.Contains(trimmed, "{") {
				continue
			}
			inLocals = true
			depth = countBracesOutsideStrings(line)
			if depth <= 0 {
				inLocals = false
				depth = 0
			}
			continue
		}
		if currentName == "" {
			if assignment := localStringAssignmentPattern.FindStringSubmatch(line); len(assignment) >= 3 {
				name := strings.TrimSpace(assignment[1])
				value := normalizeConfigAssetLiteral(strings.TrimSpace(assignment[2]))
				if name != "" && value != "" {
					assignments[name] = value
				}
			} else if assignment := localAssignmentStartPattern.FindStringSubmatch(line); len(assignment) >= 3 {
				currentName = strings.TrimSpace(assignment[1])
				currentExpression.Reset()
				currentExpression.WriteString(strings.TrimSpace(assignment[2]))
				currentParenDepth = countParensOutsideStrings(assignment[2])
				if currentParenDepth <= 0 {
					storeLocalConfigAssignment(assignments, currentName, currentExpression.String())
					currentName = ""
				}
			}
		} else {
			if trimmed != "" {
				currentExpression.WriteString("\n")
				currentExpression.WriteString(trimmed)
			}
			currentParenDepth += countParensOutsideStrings(line)
			if currentParenDepth <= 0 {
				storeLocalConfigAssignment(assignments, currentName, currentExpression.String())
				currentName = ""
			}
		}
		depth += countBracesOutsideStrings(line)
		if depth <= 0 {
			if currentName != "" {
				storeLocalConfigAssignment(assignments, currentName, currentExpression.String())
				currentName = ""
			}
			inLocals = false
			depth = 0
		}
	}
	return assignments
}

func storeLocalConfigAssignment(assignments map[string]string, name, expression string) {
	if name == "" {
		return
	}
	if value := extractConfigAssetPathFromExpression(expression); value != "" {
		assignments[name] = value
	}
}

func countBracesOutsideStrings(line string) int {
	depth := 0
	inString := false
	escaped := false
	for _, r := range line {
		switch {
		case escaped:
			escaped = false
			continue
		case r == '\\' && inString:
			escaped = true
		case r == '"':
			inString = !inString
		case !inString && r == '{':
			depth++
		case !inString && r == '}':
			depth--
		}
	}
	return depth
}

func countParensOutsideStrings(line string) int {
	depth := 0
	inString := false
	escaped := false
	for _, r := range line {
		switch {
		case escaped:
			escaped = false
		case r == '\\' && inString:
			escaped = true
		case r == '"':
			inString = !inString
		case !inString && r == '(':
			depth++
		case !inString && r == ')':
			depth--
		}
	}
	return depth
}

func extractConfigAssetPathFromExpression(expression string) string {
	for _, match := range quotedStringPattern.FindAllStringSubmatch(expression, -1) {
		if len(match) < 2 {
			continue
		}
		if value := normalizeConfigAssetLiteral(match[1]); value != "" {
			return value
		}
	}
	return ""
}

func normalizeConfigAssetLiteral(value string) string {
	trimmed := strings.TrimSpace(value)
	if trimmed == "" {
		return ""
	}
	if !strings.Contains(trimmed, "/") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".yaml") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".yml") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".json") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".tpl") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".tmpl") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".hcl") &&
		!strings.HasSuffix(strings.ToLower(trimmed), ".tf") {
		return ""
	}
	return normalizeLocalConfigAssetPath([]string{"", trimmed})
}

func appendConfigArtifactRow(rows []map[string]any, seen map[string]struct{}, pathValue, repoName, relativePath, evidenceKind string) []map[string]any {
	pathValue = strings.TrimSpace(pathValue)
	if pathValue == "" {
		return rows
	}
	key := strings.Join([]string{pathValue, repoName, relativePath, evidenceKind}, "|")
	if _, ok := seen[key]; ok {
		return rows
	}
	seen[key] = struct{}{}
	return append(rows, map[string]any{
		"path":          pathValue,
		"source_repo":   repoName,
		"relative_path": relativePath,
		"evidence_kind": evidenceKind,
	})
}

func normalizeTerragruntParentConfigPath(match []string) string {
	for _, candidate := range match[1:] {
		cleaned := strings.TrimSpace(candidate)
		if cleaned != "" {
			return normalizeLocalConfigAssetPath([]string{"", cleaned})
		}
	}
	return "terragrunt.hcl"
}

func extractKustomizeConfigPathRows(repoName string, files []FileContent) []map[string]any {
	index := make(map[string]FileContent, len(files))
	for _, file := range files {
		cleaned := cleanRepositoryRelativePath(file.RelativePath)
		if cleaned == "" {
			continue
		}
		index[cleaned] = file
	}

	kustomizationFiles := make([]string, 0)
	for relativePath := range index {
		base := strings.ToLower(path.Base(relativePath))
		if base == "kustomization.yaml" || base == "kustomization.yml" || base == "kustomization" {
			kustomizationFiles = append(kustomizationFiles, relativePath)
		}
	}
	sort.Strings(kustomizationFiles)

	rows := make([]map[string]any, 0)
	seen := map[string]struct{}{}
	for _, kustomizationPath := range kustomizationFiles {
		for _, resourceFile := range collectKustomizeResourceFiles(index, kustomizationPath) {
			for _, configPath := range extractPolicyDocumentConfigPaths(resourceFile.Content) {
				key := strings.Join([]string{repoName, resourceFile.RelativePath, configPath}, "|")
				if _, ok := seen[key]; ok {
					continue
				}
				seen[key] = struct{}{}
				rows = append(rows, map[string]any{
					"path":          configPath,
					"source_repo":   repoName,
					"relative_path": resourceFile.RelativePath,
					"evidence_kind": "kustomize_policy_document_resource",
				})
			}
		}
	}
	return rows
}

func collectKustomizeResourceFiles(index map[string]FileContent, kustomizationPath string) []FileContent {
	resourceFiles := make([]FileContent, 0)
	visitedKustomizations := map[string]struct{}{}
	seenResources := map[string]struct{}{}

	var visitKustomization func(string)
	visitKustomization = func(current string) {
		current = cleanRepositoryRelativePath(current)
		if current == "" {
			return
		}
		if _, ok := visitedKustomizations[current]; ok {
			return
		}
		visitedKustomizations[current] = struct{}{}

		file, ok := index[current]
		if !ok {
			return
		}
		refs := localKustomizeRefs(file.Content)
		baseDir := path.Dir(current)
		for _, ref := range refs {
			resolved := cleanRepositoryRelativePath(path.Join(baseDir, ref))
			if resolved == "" {
				continue
			}
			if nextKustomization, ok := resolveKustomizationTarget(index, resolved); ok {
				visitKustomization(nextKustomization)
				continue
			}
			resourceFile, ok := index[resolved]
			if !ok || !isKustomizeResourceFile(resourceFile.RelativePath) {
				continue
			}
			if _, ok := seenResources[resolved]; ok {
				continue
			}
			seenResources[resolved] = struct{}{}
			resourceFiles = append(resourceFiles, resourceFile)
		}
	}

	visitKustomization(kustomizationPath)
	sort.Slice(resourceFiles, func(i, j int) bool {
		return resourceFiles[i].RelativePath < resourceFiles[j].RelativePath
	})
	return resourceFiles
}

func localKustomizeRefs(content string) []string {
	documents, err := decodeYAMLMaps(content)
	if err != nil {
		return nil
	}

	refs := make([]string, 0)
	for _, document := range documents {
		refs = append(refs, stringSequenceValue(document["resources"])...)
		refs = append(refs, stringSequenceValue(document["bases"])...)
		refs = append(refs, stringSequenceValue(document["components"])...)
		refs = append(refs, patchPathValues(document["patches"])...)
	}

	filtered := make([]string, 0, len(refs))
	seen := map[string]struct{}{}
	for _, ref := range refs {
		if ref == "" || strings.Contains(ref, "://") {
			continue
		}
		cleaned := cleanRepositoryRelativePath(ref)
		if cleaned == "" {
			continue
		}
		if _, ok := seen[cleaned]; ok {
			continue
		}
		seen[cleaned] = struct{}{}
		filtered = append(filtered, cleaned)
	}
	sort.Strings(filtered)
	return filtered
}

func decodeYAMLMaps(content string) ([]map[string]any, error) {
	decoder := yaml.NewDecoder(strings.NewReader(content))
	documents := make([]map[string]any, 0)
	for {
		var document map[string]any
		err := decoder.Decode(&document)
		if err != nil {
			if strings.Contains(err.Error(), "EOF") {
				return documents, nil
			}
			return nil, err
		}
		if len(document) == 0 {
			continue
		}
		documents = append(documents, document)
	}
}

func stringSequenceValue(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		text := strings.TrimSpace(fmt.Sprint(item))
		if text == "" || text == "<nil>" {
			continue
		}
		result = append(result, text)
	}
	return result
}

func patchPathValues(value any) []string {
	items, ok := value.([]any)
	if !ok {
		return nil
	}
	result := make([]string, 0, len(items))
	for _, item := range items {
		object, ok := item.(map[string]any)
		if !ok {
			continue
		}
		pathValue := strings.TrimSpace(fmt.Sprint(object["path"]))
		if pathValue == "" || pathValue == "<nil>" {
			continue
		}
		result = append(result, pathValue)
	}
	return result
}

func resolveKustomizationTarget(index map[string]FileContent, resolved string) (string, bool) {
	if file, ok := index[resolved]; ok && isKustomizationFile(file.RelativePath) {
		return resolved, true
	}
	for _, candidate := range []string{"kustomization.yaml", "kustomization.yml", "kustomization"} {
		joined := cleanRepositoryRelativePath(path.Join(resolved, candidate))
		if _, ok := index[joined]; ok {
			return joined, true
		}
	}
	return "", false
}

func isKustomizeResourceFile(relativePath string) bool {
	lower := strings.ToLower(relativePath)
	return strings.HasSuffix(lower, ".yaml") || strings.HasSuffix(lower, ".yml") || strings.HasSuffix(lower, ".json")
}

func isKustomizationFile(relativePath string) bool {
	base := strings.ToLower(path.Base(relativePath))
	return base == "kustomization.yaml" || base == "kustomization.yml" || base == "kustomization"
}

func extractPolicyDocumentConfigPaths(content string) []string {
	documents, err := decodeYAMLMaps(content)
	if err != nil {
		return nil
	}

	paths := make([]string, 0)
	seen := map[string]struct{}{}
	for _, document := range documents {
		walkPolicyDocumentResources(document, func(resource string) {
			configPath := normalizeConfigPath(resource)
			if configPath == "" {
				return
			}
			if _, ok := seen[configPath]; ok {
				return
			}
			seen[configPath] = struct{}{}
			paths = append(paths, configPath)
		})
	}
	sort.Strings(paths)
	return paths
}

func walkPolicyDocumentResources(value any, emit func(string)) {
	switch typed := value.(type) {
	case map[string]any:
		for key, child := range typed {
			if strings.EqualFold(key, "Resource") {
				for _, resource := range flattenStringValues(child) {
					emit(resource)
				}
			}
			walkPolicyDocumentResources(child, emit)
		}
	case []any:
		for _, child := range typed {
			walkPolicyDocumentResources(child, emit)
		}
	}
}

func flattenStringValues(value any) []string {
	switch typed := value.(type) {
	case string:
		trimmed := strings.TrimSpace(typed)
		if trimmed == "" {
			return nil
		}
		return []string{trimmed}
	case []any:
		values := make([]string, 0, len(typed))
		for _, item := range typed {
			values = append(values, flattenStringValues(item)...)
		}
		return values
	default:
		return nil
	}
}

func normalizeConfigPath(value string) string {
	value = strings.TrimSpace(value)
	if value == "" {
		return ""
	}
	if match := ssmParameterARNPattern.FindStringSubmatch(value); len(match) == 2 {
		return match[1]
	}
	if match := ssmConfigPathPattern.FindStringSubmatch(value); len(match) == 2 {
		return match[1]
	}
	return ""
}

func normalizeLocalConfigAssetPath(match []string) string {
	if len(match) < 2 {
		return ""
	}
	value := strings.TrimSpace(match[1])
	if value == "" {
		return ""
	}
	if strings.Contains(value, "://") || strings.HasPrefix(strings.ToLower(value), "git::") || strings.HasPrefix(strings.ToLower(value), "tfr:///") {
		return ""
	}
	replacer := strings.NewReplacer(
		"${path.module}/", "",
		"${path_relative_to_include()}/", "",
		"${path_relative_to_include()}", "",
		"${get_repo_root()}/", "",
		"${get_parent_terragrunt_dir()}/", "",
		"${get_terragrunt_dir()}/", "",
	)
	value = replacer.Replace(value)
	value = strings.TrimPrefix(value, "./")
	value = strings.TrimSpace(value)
	if value == "" || value == "." {
		return ""
	}
	return cleanRepositoryRelativePath(value)
}

func cleanRepositoryRelativePath(relativePath string) string {
	relativePath = path.Clean(strings.TrimSpace(relativePath))
	switch relativePath {
	case "", ".", "/":
		return ""
	default:
		return strings.TrimPrefix(relativePath, "./")
	}
}
