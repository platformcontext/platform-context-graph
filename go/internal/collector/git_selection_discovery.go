package collector

import (
	"fmt"
	"io/fs"
	"os"
	"path/filepath"
	"sort"
	"strings"
)

// GitHubRepositoryRecord is one GitHub discovery candidate for repository selection.
type GitHubRepositoryRecord struct {
	RepoID   string
	Archived bool
}

// RepositorySelection holds the selected repository identifiers for one sync cycle.
type RepositorySelection struct {
	RepositoryIDs         []string
	ArchivedRepositoryIDs []string
}

// GitSyncSelection captures the repo paths selected after one Git-backed sync pass.
type GitSyncSelection struct {
	SelectedRepoPaths []string
}

func selectGitHubRepositoryIDs(
	repositories []GitHubRepositoryRecord,
	repositoryRules []RepoSyncRepositoryRule,
	includeArchivedRepos bool,
) RepositorySelection {
	exactRules := make(map[string]struct{})
	for _, rule := range repositoryRules {
		if strings.ToLower(strings.TrimSpace(rule.Kind)) != "exact" {
			continue
		}
		exactRules[normalizeRepositoryID(rule.Value)] = struct{}{}
	}

	selectable := make([]string, 0, len(repositories))
	archived := make([]string, 0)
	seenSelectable := make(map[string]struct{})
	seenArchived := make(map[string]struct{})
	for _, repository := range repositories {
		repoID := normalizeRepositoryID(repository.RepoID)
		if repoID == "" {
			continue
		}
		_, explicitlyAllowedArchived := exactRules[repoID]
		if repository.Archived && !includeArchivedRepos && !explicitlyAllowedArchived {
			if _, ok := seenArchived[repoID]; !ok {
				seenArchived[repoID] = struct{}{}
				archived = append(archived, repoID)
			}
			continue
		}
		if _, ok := seenSelectable[repoID]; ok {
			continue
		}
		seenSelectable[repoID] = struct{}{}
		selectable = append(selectable, repoID)
	}
	if len(repositoryRules) == 0 {
		return RepositorySelection{
			RepositoryIDs:         selectable,
			ArchivedRepositoryIDs: archived,
		}
	}

	selected := make([]string, 0, len(selectable))
	for _, repoID := range selectable {
		for _, rule := range repositoryRules {
			if rule.Matches(repoID) {
				selected = append(selected, repoID)
				break
			}
		}
	}
	return RepositorySelection{
		RepositoryIDs:         selected,
		ArchivedRepositoryIDs: archived,
	}
}

func discoverFilesystemRepositoryIDs(filesystemRoot string) ([]string, error) {
	root, err := filepath.Abs(strings.TrimSpace(filesystemRoot))
	if err != nil {
		return nil, fmt.Errorf("resolve filesystem root %q: %w", filesystemRoot, err)
	}
	if resolved, resolveErr := filepath.EvalSymlinks(root); resolveErr == nil {
		root = resolved
	}
	info, err := os.Stat(root)
	if err != nil {
		return nil, fmt.Errorf("stat filesystem root %q: %w", filesystemRoot, err)
	}
	if !info.IsDir() {
		return nil, fmt.Errorf("filesystem root %q is not a directory", filesystemRoot)
	}

	repoRoots, err := discoverRepoRoots(root)
	if err != nil {
		return nil, err
	}
	if len(repoRoots) == 1 && repoRoots[0] == root {
		return []string{"."}, nil
	}
	repoIDs := make([]string, 0, len(repoRoots))
	for _, repoRoot := range repoRoots {
		if repoRoot == root {
			continue
		}
		rel, err := filepath.Rel(root, repoRoot)
		if err != nil {
			return nil, fmt.Errorf("relative filesystem repo path %q: %w", repoRoot, err)
		}
		repoIDs = append(repoIDs, filepath.ToSlash(filepath.Clean(rel)))
	}
	sort.Strings(repoIDs)
	return repoIDs, nil
}

func discoverRepoRoots(root string) ([]string, error) {
	if repositoryRootLike(root) {
		return []string{root}, nil
	}

	entries, err := os.ReadDir(root)
	if err != nil {
		return nil, fmt.Errorf("read filesystem root %q: %w", root, err)
	}
	repoRoots := make([]string, 0)
	for _, entry := range entries {
		if !entry.IsDir() {
			continue
		}
		child := filepath.Join(root, entry.Name())
		discovered, err := discoverRepoRoots(child)
		if err != nil {
			return nil, err
		}
		repoRoots = append(repoRoots, discovered...)
	}
	return repoRoots, nil
}

func repositoryRootLike(path string) bool {
	if hasGitMarker(path) {
		return true
	}

	childDirectories := 0
	entries, err := os.ReadDir(path)
	if err != nil {
		return false
	}
	for _, entry := range entries {
		if entry.IsDir() {
			childDirectories++
			continue
		}
		if entry.Name() == ".DS_Store" {
			continue
		}
		return true
	}
	return childDirectories == 0
}

func hasGitMarker(dir string) bool {
	info, err := os.Stat(filepath.Join(dir, ".git"))
	if err != nil {
		return false
	}
	return info.IsDir() || info.Mode().IsRegular() || info.Mode()&os.ModeSymlink != 0
}

func repoCheckoutName(repoID string) (string, error) {
	normalized := normalizeRepositoryID(repoID)
	if normalized == "" {
		return "", fmt.Errorf("invalid repository identifier %q", repoID)
	}
	return normalized, nil
}

func repoRemoteURL(config RepoSyncConfig, repoID string) string {
	slug := normalizeRepositoryID(repoID)
	if slug == "" {
		return ""
	}
	if !strings.Contains(slug, "/") && strings.TrimSpace(config.GithubOrg) != "" {
		slug = config.GithubOrg + "/" + slug
	}
	if strings.ToLower(strings.TrimSpace(config.GitAuthMethod)) == "ssh" {
		return "git@github.com:" + slug + ".git"
	}
	return "https://github.com/" + slug + ".git"
}

func repoIDFromManagedPath(reposDir string, repoPath string) string {
	reposDir, err := filepath.Abs(reposDir)
	if err != nil {
		return ""
	}
	repoPath, err = filepath.Abs(repoPath)
	if err != nil {
		return ""
	}
	rel, err := filepath.Rel(reposDir, repoPath)
	if err != nil {
		return ""
	}
	if rel == "." || strings.HasPrefix(rel, "..") {
		return ""
	}
	return filepath.ToSlash(filepath.Clean(rel))
}

func walkManagedRepositoryRoots(root string) ([]string, error) {
	root, err := filepath.Abs(root)
	if err != nil {
		return nil, fmt.Errorf("resolve repos dir %q: %w", root, err)
	}
	roots := make([]string, 0)
	err = filepath.WalkDir(root, func(current string, entry fs.DirEntry, walkErr error) error {
		if walkErr != nil {
			return walkErr
		}
		if current == root {
			return nil
		}
		if !entry.IsDir() {
			return nil
		}
		if _, err := os.Stat(filepath.Join(current, ".git")); err == nil {
			roots = append(roots, current)
			return filepath.SkipDir
		}
		return nil
	})
	if err != nil && !os.IsNotExist(err) {
		return nil, err
	}
	sort.Strings(roots)
	return roots, nil
}
