package relationships

import (
	"regexp"
	"strings"
)

var jenkinsGitHubRepoPattern = regexp.MustCompile(`(?i)github\.com[:/][^/"'\s]+/([A-Za-z0-9._-]+)(?:\.git)?`)

func discoverJenkinsEvidence(
	sourceRepoID, filePath, content string,
	parsedFileData map[string]any,
	catalog []CatalogEntry,
	seen map[evidenceKey]struct{},
) []EvidenceFact {
	var evidence []EvidenceFact

	for _, library := range jenkinsSharedLibraries(parsedFileData) {
		evidence = append(evidence, matchCatalog(
			sourceRepoID, library, filePath,
			EvidenceKindJenkinsSharedLibrary, RelDiscoversConfigIn, 0.89,
			"Jenkins shared library references configuration or automation in the target repository",
			"jenkins", catalog, seen, map[string]any{
				"shared_library": library,
			},
		)...)
	}

	for _, repoRef := range jenkinsGitHubRepoRefs(content, parsedFileData) {
		evidence = append(evidence, matchCatalog(
			sourceRepoID, repoRef, filePath,
			EvidenceKindJenkinsGitHubRepository, RelDiscoversConfigIn, 0.92,
			"Jenkins pipeline references the target repository through an explicit GitHub URL",
			"jenkins", catalog, seen, map[string]any{
				"repository_ref": repoRef,
			},
		)...)
	}

	return evidence
}

func jenkinsSharedLibraries(parsedFileData map[string]any) []string {
	if len(parsedFileData) == 0 {
		return nil
	}
	values := payloadAnyStringSlice(parsedFileData["shared_libraries"])
	libs := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if at := strings.Index(value, "@"); at >= 0 {
			value = value[:at]
		}
		if value == "" {
			continue
		}
		libs = append(libs, value)
	}
	return uniqueStrings(libs)
}

func jenkinsGitHubRepoRefs(content string, parsedFileData map[string]any) []string {
	candidates := make([]string, 0)
	for _, match := range jenkinsGitHubRepoPattern.FindAllStringSubmatch(content, -1) {
		if len(match) >= 2 {
			candidates = append(candidates, strings.TrimSpace(match[1]))
		}
	}

	for _, command := range payloadAnyStringSlice(parsedFileData["shell_commands"]) {
		for _, match := range jenkinsGitHubRepoPattern.FindAllStringSubmatch(command, -1) {
			if len(match) >= 2 {
				candidates = append(candidates, strings.TrimSpace(match[1]))
			}
		}
	}

	return uniqueStrings(candidates)
}

func payloadAnyStringSlice(value any) []string {
	switch typed := value.(type) {
	case []string:
		return typed
	case []any:
		result := make([]string, 0, len(typed))
		for _, item := range typed {
			text, ok := item.(string)
			if ok {
				result = append(result, text)
			}
		}
		return result
	default:
		return nil
	}
}
