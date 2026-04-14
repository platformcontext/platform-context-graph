package collector

import (
	"os"
	"path/filepath"
	"testing"
)

func TestRepositoryRootLikeWithGitMarker(t *testing.T) {
	dir := t.TempDir()
	if err := os.Mkdir(filepath.Join(dir, ".git"), 0o755); err != nil {
		t.Fatal(err)
	}
	if !repositoryRootLike(dir) {
		t.Error("expected directory with .git to be root-like")
	}
}

func TestRepositoryRootLikeWithVisibleFile(t *testing.T) {
	dir := t.TempDir()
	if err := os.WriteFile(filepath.Join(dir, "main.tf"), []byte("# tf"), 0o644); err != nil {
		t.Fatal(err)
	}
	if !repositoryRootLike(dir) {
		t.Error("expected directory with visible file to be root-like")
	}
}

func TestRepositoryRootLikeSkipsDotfiles(t *testing.T) {
	dir := t.TempDir()
	// Create only hidden files and subdirectories — should NOT be root-like.
	if err := os.WriteFile(filepath.Join(dir, ".envrc"), []byte("layout go"), 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, ".DS_Store"), []byte{0}, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, ".omc"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "org-a"), 0o755); err != nil {
		t.Fatal(err)
	}
	if err := os.Mkdir(filepath.Join(dir, "org-b"), 0o755); err != nil {
		t.Fatal(err)
	}
	if repositoryRootLike(dir) {
		t.Error("directory with only dotfiles and subdirectories should NOT be root-like")
	}
}

func TestRepositoryRootLikeEmptyDir(t *testing.T) {
	dir := t.TempDir()
	// Empty directory with no children is treated as a leaf (root-like).
	if !repositoryRootLike(dir) {
		t.Error("expected empty directory to be root-like")
	}
}

func TestDiscoverRepoRootsNestedOrganizations(t *testing.T) {
	// Simulate: root/ has .envrc + org-a/ + org-b/
	//   org-a/ has repo-1/ (with .git) and repo-2/ (with .git)
	//   org-b/ has repo-3/ (with .git)
	root := t.TempDir()
	if err := os.WriteFile(filepath.Join(root, ".envrc"), []byte("layout go"), 0o644); err != nil {
		t.Fatal(err)
	}

	repos := []string{
		"org-a/repo-1",
		"org-a/repo-2",
		"org-b/repo-3",
	}
	for _, repo := range repos {
		repoDir := filepath.Join(root, filepath.FromSlash(repo))
		if err := os.MkdirAll(filepath.Join(repoDir, ".git"), 0o755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(filepath.Join(repoDir, "main.go"), []byte("package main"), 0o644); err != nil {
			t.Fatal(err)
		}
	}

	ids, err := discoverFilesystemRepositoryIDs(root)
	if err != nil {
		t.Fatalf("discover failed: %v", err)
	}
	if len(ids) != 3 {
		t.Fatalf("expected 3 repos, got %d: %v", len(ids), ids)
	}

	expected := map[string]bool{
		"org-a/repo-1": true,
		"org-a/repo-2": true,
		"org-b/repo-3": true,
	}
	for _, id := range ids {
		if !expected[id] {
			t.Errorf("unexpected repo ID: %s", id)
		}
	}
}
