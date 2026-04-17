package parser

import (
	"path"
	"regexp"
	"sort"
	"strings"
)

var (
	terragruntReadConfigPattern          = regexp.MustCompile(`(?i)read_terragrunt_config\((?:find_in_parent_folders\()?"([^"]+)"`)
	terragruntFindInParentFoldersPattern = regexp.MustCompile(`(?i)find_in_parent_folders\("([^"]+)"\)`)
	terragruntIncludePathPattern         = regexp.MustCompile(`(?i)\bpath\s*=\s*find_in_parent_folders\("([^"]+)"\)`)
	localFileFunctionPattern             = regexp.MustCompile(`(?i)\b(?:file|templatefile)\(\s*"([^"]+)"`)
)

type terragruntHelperPaths struct {
	includePaths             []string
	readConfigPaths          []string
	findInParentFoldersPaths []string
	localConfigAssetPaths    []string
}

func parseTerragruntHelperPaths(source []byte) terragruntHelperPaths {
	content := string(source)
	return terragruntHelperPaths{
		includePaths:             collectNormalizedHelperPaths(content, terragruntIncludePathPattern),
		readConfigPaths:          collectNormalizedHelperPaths(content, terragruntReadConfigPattern),
		findInParentFoldersPaths: collectNormalizedHelperPaths(content, terragruntFindInParentFoldersPattern),
		localConfigAssetPaths:    collectNormalizedHelperPaths(content, localFileFunctionPattern),
	}
}

func collectNormalizedHelperPaths(content string, pattern *regexp.Regexp) []string {
	matches := pattern.FindAllStringSubmatch(content, -1)
	if len(matches) == 0 {
		return nil
	}

	seen := make(map[string]struct{}, len(matches))
	paths := make([]string, 0, len(matches))
	for _, match := range matches {
		normalized := normalizeLocalConfigAssetPath(match)
		if normalized == "" {
			continue
		}
		if _, ok := seen[normalized]; ok {
			continue
		}
		seen[normalized] = struct{}{}
		paths = append(paths, normalized)
	}
	sort.Strings(paths)
	return paths
}

func normalizeLocalConfigAssetPath(match []string) string {
	if len(match) < 2 {
		return ""
	}
	value := strings.TrimSpace(match[1])
	if value == "" {
		return ""
	}
	if strings.Contains(value, "://") ||
		strings.HasPrefix(strings.ToLower(value), "git::") ||
		strings.HasPrefix(strings.ToLower(value), "tfr:///") {
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
