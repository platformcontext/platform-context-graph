package collector

import (
	"encoding/json"
	"fmt"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"runtime"
	"sort"
	"strconv"
	"strings"
)

// RepoSyncRepositoryRule constrains repository selection for one sync cycle.
type RepoSyncRepositoryRule struct {
	Kind  string
	Value string
}

// Matches reports whether the repository identifier matches the configured rule.
func (r RepoSyncRepositoryRule) Matches(repositoryID string) bool {
	switch strings.TrimSpace(strings.ToLower(r.Kind)) {
	case "exact":
		return normalizeRepositoryID(repositoryID) == normalizeRepositoryID(r.Value)
	case "regex":
		pattern := strings.TrimSpace(r.Value)
		if pattern == "" {
			return false
		}
		matched, err := regexp.MatchString(pattern, normalizeRepositoryID(repositoryID))
		return err == nil && matched
	default:
		return false
	}
}

// RepoSyncConfig captures the environment-driven sync contract for Go-owned runtimes.
type RepoSyncConfig struct {
	ReposDir              string
	SourceMode            string
	GitAuthMethod         string
	GithubOrg             string
	Repositories          []string
	FilesystemRoot        string
	FilesystemDirect      bool
	CloneDepth            int
	RepoLimit             int
	Component             string
	RepositoryRules       []RepoSyncRepositoryRule
	IncludeArchivedRepos  bool
	GitToken              string
	GitHubAppID           string
	GitHubAppInstallation string
	GitHubAppPrivateKey   string
	SSHPrivateKeyPath     string
	SSHKnownHostsPath     string
	DependencyMode        bool
	DependencyName        string
	DependencyLanguage    string
	FileTargets            []string
	SnapshotWorkers        int
	ParseWorkers           int
	LargeRepoThreshold     int
	LargeRepoMaxConcurrent int
}

// LoadRepoSyncConfig parses the repo-sync environment contract for Go runtimes.
func LoadRepoSyncConfig(component string, getenv func(string) string) (RepoSyncConfig, error) {
	if getenv == nil {
		return RepoSyncConfig{}, fmt.Errorf("repo sync getenv is required")
	}

	sourceMode := strings.TrimSpace(getenv("PCG_REPO_SOURCE_MODE"))
	if sourceMode == "" {
		sourceMode = "githubOrg"
	}
	repositoryRules, err := parseRepositoryRulesJSON(getenv("PCG_REPOSITORY_RULES_JSON"))
	if err != nil {
		return RepoSyncConfig{}, err
	}
	if err := validateRepositoryRulesForSourceMode(sourceMode, repositoryRules); err != nil {
		return RepoSyncConfig{}, err
	}

	reposDir := strings.TrimSpace(getenv("PCG_REPOS_DIR"))
	if reposDir == "" {
		reposDir = "/data/repos"
	}
	gitAuthMethod := strings.TrimSpace(getenv("PCG_GIT_AUTH_METHOD"))
	if gitAuthMethod == "" {
		gitAuthMethod = "githubApp"
	}
	cloneDepth := intFromEnv(getenv, "PCG_CLONE_DEPTH", 1)
	repoLimit := intFromEnv(getenv, "PCG_REPO_LIMIT", 4000)

	config := RepoSyncConfig{
		ReposDir:              reposDir,
		SourceMode:            sourceMode,
		GitAuthMethod:         gitAuthMethod,
		GithubOrg:             strings.TrimSpace(getenv("PCG_GITHUB_ORG")),
		Repositories:          extractExactRepositoryIDs(sourceMode, repositoryRules),
		FilesystemRoot:        strings.TrimSpace(getenv("PCG_FILESYSTEM_ROOT")),
		FilesystemDirect:      boolFromEnv(getenv("PCG_FILESYSTEM_DIRECT")),
		CloneDepth:            cloneDepth,
		RepoLimit:             repoLimit,
		Component:             component,
		RepositoryRules:       repositoryRules,
		IncludeArchivedRepos:  boolFromEnv(getenv("PCG_INCLUDE_ARCHIVED_REPOS")),
		GitToken:              firstNonEmpty(getenv("PCG_GIT_TOKEN"), getenv("GITHUB_TOKEN")),
		GitHubAppID:           firstNonEmpty(getenv("GITHUB_APP_ID"), getenv("PCG_GITHUB_APP_ID")),
		GitHubAppInstallation: firstNonEmpty(getenv("GITHUB_APP_INSTALLATION_ID"), getenv("PCG_GITHUB_APP_INSTALLATION_ID")),
		GitHubAppPrivateKey:   firstNonEmpty(getenv("GITHUB_APP_PRIVATE_KEY"), getenv("PCG_GITHUB_APP_PRIVATE_KEY")),
		SSHPrivateKeyPath:     strings.TrimSpace(getenv("PCG_SSH_PRIVATE_KEY_PATH")),
		SSHKnownHostsPath:     strings.TrimSpace(getenv("PCG_SSH_KNOWN_HOSTS_PATH")),
		DependencyMode:        boolFromEnv(getenv("PCG_BOOTSTRAP_IS_DEPENDENCY")),
		DependencyName:        strings.TrimSpace(getenv("PCG_BOOTSTRAP_PACKAGE_NAME")),
		DependencyLanguage:    strings.TrimSpace(getenv("PCG_BOOTSTRAP_PACKAGE_LANGUAGE")),
		SnapshotWorkers:        snapshotWorkerCount(getenv),
		ParseWorkers:           parseWorkerCount(getenv),
		LargeRepoThreshold:     largeRepoThreshold(getenv),
		LargeRepoMaxConcurrent: largeRepoMaxConcurrent(getenv),
	}
	normalizeFilesystemConfig(&config)
	return config, nil
}

func normalizeFilesystemConfig(config *RepoSyncConfig) {
	if config == nil || strings.TrimSpace(config.SourceMode) != "filesystem" {
		return
	}

	root := strings.TrimSpace(config.FilesystemRoot)
	if root == "" {
		return
	}

	absoluteRoot, err := filepath.Abs(root)
	if err != nil {
		return
	}
	if resolvedRoot, resolveErr := filepath.EvalSymlinks(absoluteRoot); resolveErr == nil {
		absoluteRoot = resolvedRoot
	}

	info, err := os.Stat(absoluteRoot)
	if err != nil {
		config.FilesystemRoot = absoluteRoot
		return
	}
	if info.IsDir() {
		config.FilesystemRoot = absoluteRoot
		return
	}

	config.FileTargets = []string{absoluteRoot}
	config.FilesystemRoot = filepath.Dir(absoluteRoot)
}

func extractExactRepositoryIDs(
	sourceMode string,
	rules []RepoSyncRepositoryRule,
) []string {
	if sourceMode != "explicit" && sourceMode != "filesystem" {
		return nil
	}

	seen := make(map[string]struct{})
	exact := make([]string, 0, len(rules))
	for _, rule := range rules {
		if strings.TrimSpace(strings.ToLower(rule.Kind)) != "exact" {
			continue
		}
		repositoryID := normalizeRepositoryID(rule.Value)
		if repositoryID == "" {
			continue
		}
		if _, ok := seen[repositoryID]; ok {
			continue
		}
		seen[repositoryID] = struct{}{}
		exact = append(exact, repositoryID)
	}
	return exact
}

func validateRepositoryRulesForSourceMode(
	sourceMode string,
	rules []RepoSyncRepositoryRule,
) error {
	if sourceMode != "explicit" && sourceMode != "filesystem" {
		return nil
	}
	nonExact := make([]string, 0)
	for _, rule := range rules {
		if strings.TrimSpace(strings.ToLower(rule.Kind)) == "exact" {
			continue
		}
		nonExact = append(nonExact, rule.Value)
	}
	if len(nonExact) == 0 {
		return nil
	}
	return fmt.Errorf(
		"PCG_REPOSITORY_RULES_JSON only supports exact rules when PCG_REPO_SOURCE_MODE=%q; found non-exact rules: %v",
		sourceMode,
		nonExact,
	)
}

func parseRepositoryRulesJSON(raw string) ([]RepoSyncRepositoryRule, error) {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return nil, nil
	}

	var parsed any
	if err := json.Unmarshal([]byte(raw), &parsed); err != nil {
		return nil, fmt.Errorf("parse PCG_REPOSITORY_RULES_JSON: %w", err)
	}

	switch value := parsed.(type) {
	case []any:
		rules := make([]RepoSyncRepositoryRule, 0, len(value))
		for _, item := range value {
			switch typed := item.(type) {
			case string:
				repositoryID := normalizeRepositoryID(typed)
				if repositoryID != "" {
					rules = append(rules, RepoSyncRepositoryRule{Kind: "exact", Value: repositoryID})
				}
			case map[string]any:
				rule, err := repositoryRuleFromMap(typed)
				if err != nil {
					return nil, err
				}
				rules = append(rules, rule)
			default:
				return nil, fmt.Errorf("unsupported repository rule entry: %T", item)
			}
		}
		return rules, nil
	case map[string]any:
		rules := make([]RepoSyncRepositoryRule, 0)
		for _, item := range valuesFromRuleMap(value["exact"]) {
			repositoryID := normalizeRepositoryID(item)
			if repositoryID != "" {
				rules = append(rules, RepoSyncRepositoryRule{Kind: "exact", Value: repositoryID})
			}
		}
		for _, item := range valuesFromRuleMap(value["regex"]) {
			pattern := strings.TrimSpace(item)
			if pattern != "" {
				rules = append(rules, RepoSyncRepositoryRule{Kind: "regex", Value: pattern})
			}
		}
		if len(rules) == 0 {
			return nil, fmt.Errorf(
				"PCG_REPOSITORY_RULES_JSON must be a JSON list of rules or an object with exact/regex keys",
			)
		}
		return rules, nil
	default:
		return nil, fmt.Errorf(
			"PCG_REPOSITORY_RULES_JSON must be a JSON list of rules or an object with exact/regex keys",
		)
	}
}

func repositoryRuleFromMap(raw map[string]any) (RepoSyncRepositoryRule, error) {
	if exactValue, ok := raw["exact"]; ok && len(raw) == 1 {
		repositoryID := normalizeRepositoryID(fmt.Sprint(exactValue))
		return RepoSyncRepositoryRule{Kind: "exact", Value: repositoryID}, nil
	}
	if regexValue, ok := raw["regex"]; ok && len(raw) == 1 {
		return RepoSyncRepositoryRule{Kind: "regex", Value: strings.TrimSpace(fmt.Sprint(regexValue))}, nil
	}

	kind := firstNonEmpty(
		stringValue(raw["type"]),
		stringValue(raw["kind"]),
		stringValue(raw["match"]),
	)
	value := firstNonEmpty(stringValue(raw["value"]), stringValue(raw["pattern"]))
	kind = strings.ToLower(strings.TrimSpace(kind))
	switch kind {
	case "exact":
		return RepoSyncRepositoryRule{Kind: "exact", Value: normalizeRepositoryID(value)}, nil
	case "regex":
		return RepoSyncRepositoryRule{Kind: "regex", Value: strings.TrimSpace(value)}, nil
	default:
		return RepoSyncRepositoryRule{}, fmt.Errorf("unsupported repository rule mapping: %#v", raw)
	}
}

func valuesFromRuleMap(raw any) []string {
	switch value := raw.(type) {
	case nil:
		return nil
	case string:
		return []string{value}
	case []any:
		items := make([]string, 0, len(value))
		for _, item := range value {
			items = append(items, fmt.Sprint(item))
		}
		return items
	default:
		return []string{fmt.Sprint(value)}
	}
}

func normalizeRepositoryID(raw string) string {
	raw = strings.TrimSpace(raw)
	if raw == "" {
		return ""
	}
	parts := strings.FieldsFunc(raw, func(r rune) bool {
		return r == '/' || r == '\\'
	})
	clean := make([]string, 0, len(parts))
	for _, part := range parts {
		part = strings.TrimSpace(part)
		if part == "" || part == "." || part == ".." {
			continue
		}
		clean = append(clean, part)
	}
	return path.Clean(strings.Join(clean, "/"))
}

func intFromEnv(getenv func(string) string, key string, defaultValue int) int {
	raw := strings.TrimSpace(getenv(key))
	if raw == "" {
		return defaultValue
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return defaultValue
	}
	return value
}

func boolFromEnv(raw string) bool {
	switch strings.ToLower(strings.TrimSpace(raw)) {
	case "1", "true", "yes", "on":
		return true
	default:
		return false
	}
}

func firstNonEmpty(values ...string) string {
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value != "" {
			return value
		}
	}
	return ""
}

func stringValue(raw any) string {
	if raw == nil {
		return ""
	}
	return strings.TrimSpace(fmt.Sprint(raw))
}

func sortUniqueStrings(values []string) []string {
	seen := make(map[string]struct{}, len(values))
	result := make([]string, 0, len(values))
	for _, value := range values {
		value = strings.TrimSpace(value)
		if value == "" {
			continue
		}
		if _, ok := seen[value]; ok {
			continue
		}
		seen[value] = struct{}{}
		result = append(result, value)
	}
	sort.Strings(result)
	return result
}

// snapshotWorkerCount returns the number of concurrent snapshot workers.
// Reads PCG_SNAPSHOT_WORKERS from env; defaults to min(NumCPU, 4).
func snapshotWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_SNAPSHOT_WORKERS")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := runtime.NumCPU()
	if n > 4 {
		n = 4
	}
	if n < 1 {
		n = 1
	}
	return n
}

// parseWorkerCount returns the number of concurrent file parse workers.
// Reads PCG_PARSE_WORKERS from env; defaults to min(NumCPU, 8).
func parseWorkerCount(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_PARSE_WORKERS")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	n := runtime.NumCPU()
	if n > 8 {
		n = 8
	}
	if n < 1 {
		n = 1
	}
	return n
}

// largeRepoThreshold returns the file-count threshold above which a repository
// is classified as "large" for concurrency limiting.
// Reads PCG_LARGE_REPO_FILE_THRESHOLD from env; defaults to 1000.
//
// Production data (895 repos, Apr 2026) shows 34 repos above 1000 files
// producing 66.8% of all facts. Repos in the 501–1000 range (40 repos)
// are busy but not memory-dangerous and benefit from full parallelism.
func largeRepoThreshold(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_LARGE_REPO_FILE_THRESHOLD")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	return 1000
}

// largeRepoMaxConcurrent returns the maximum number of large repositories that
// can be snapshotted concurrently.
// Reads PCG_LARGE_REPO_MAX_CONCURRENT from env; defaults to 2.
//
// Tuning guide:
//
//	1 = safest for memory; only one large parse at a time
//	2 = good balance; two large repos + remaining workers on small repos
//	4 = aggressive; requires more RAM but faster on large-heavy workloads
func largeRepoMaxConcurrent(getenv func(string) string) int {
	if raw := strings.TrimSpace(getenv("PCG_LARGE_REPO_MAX_CONCURRENT")); raw != "" {
		if n, err := strconv.Atoi(raw); err == nil && n > 0 {
			return n
		}
	}
	return 2
}
