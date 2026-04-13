package discovery

import (
	"os"
	"path/filepath"
	"reflect"
	"testing"
)

func TestResolveRepositoryFileSetsHonorsHiddenPolicySupportedMatcherAndOrdering(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	repoA := filepath.Join(root, "repo-a")
	repoB := filepath.Join(root, "repo-b")
	nestedRepo := filepath.Join(repoA, "submodule")

	mustMkdirGit(t, repoA)
	mustMkdirGit(t, repoB)
	mustMkdirGit(t, nestedRepo)

	mustWriteFile(t, filepath.Join(root, ".gitignore"), "*.py\n")
	mustWriteFile(t, filepath.Join(repoA, ".gitignore"), "ignored.py\n")
	mustWriteFile(t, filepath.Join(repoA, "kept.py"), "print('kept')\n")
	mustWriteFile(t, filepath.Join(repoA, "ignored.py"), "print('ignored')\n")
	mustWriteFile(t, filepath.Join(repoA, "Dockerfile"), "FROM scratch\n")
	mustWriteFile(t, filepath.Join(repoA, ".github", "workflows", "deploy.yaml"), "name: deploy\n")
	mustWriteFile(t, filepath.Join(repoA, ".github", "secret.py"), "print('secret')\n")
	mustWriteFile(t, filepath.Join(repoA, ".hidden", "skip.py"), "print('skip')\n")
	mustWriteFile(t, filepath.Join(nestedRepo, "nested.py"), "print('nested')\n")
	mustWriteFile(t, filepath.Join(repoB, "b.py"), "print('b')\n")

	got, err := ResolveRepositoryFileSets(
		root,
		supportedPathMatcher,
		Options{
			IgnoredDirs:             []string{".git", "node_modules", "vendor"},
			IgnoreHidden:            true,
			PreservedHiddenPrefixes: []string{".github/workflows"},
			HonorGitignore:          false,
		},
	)
	if err != nil {
		t.Fatalf("ResolveRepositoryFileSets() error = %v, want nil", err)
	}

	want := []RepoFileSet{
		{
			RepoRoot: mustResolvePath(t, repoA),
			Files: []string{
				mustResolvePath(t, filepath.Join(repoA, ".github", "workflows", "deploy.yaml")),
				mustResolvePath(t, filepath.Join(repoA, "Dockerfile")),
				mustResolvePath(t, filepath.Join(repoA, "ignored.py")),
				mustResolvePath(t, filepath.Join(repoA, "kept.py")),
			},
		},
		{
			RepoRoot: mustResolvePath(t, nestedRepo),
			Files: []string{
				mustResolvePath(t, filepath.Join(nestedRepo, "nested.py")),
			},
		},
		{
			RepoRoot: mustResolvePath(t, repoB),
			Files: []string{
				mustResolvePath(t, filepath.Join(repoB, "b.py")),
			},
		},
	}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ResolveRepositoryFileSets() = %#v, want %#v", got, want)
	}
}

func TestResolveRepositoryFileSetsHonorsRepoLocalGitignoreScopingAndNestedNegation(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	repo := filepath.Join(root, "repo")
	nested := filepath.Join(repo, "generated")

	mustMkdirGit(t, repo)

	mustWriteFile(t, filepath.Join(root, ".gitignore"), "*.py\n")
	mustWriteFile(t, filepath.Join(repo, ".gitignore"), "ignored.py\n")
	mustWriteFile(t, filepath.Join(nested, ".gitignore"), "*\n!keep.py\n")
	mustWriteFile(t, filepath.Join(repo, "kept.py"), "print('kept')\n")
	mustWriteFile(t, filepath.Join(repo, "ignored.py"), "print('ignored')\n")
	mustWriteFile(t, filepath.Join(nested, "keep.py"), "print('keep')\n")
	mustWriteFile(t, filepath.Join(nested, "drop.py"), "print('drop')\n")

	got, err := ResolveRepositoryFileSets(
		root,
		func(path string) bool {
			return filepath.Ext(path) == ".py"
		},
		Options{
			IgnoredDirs:    []string{".git"},
			IgnoreHidden:   false,
			HonorGitignore: true,
		},
	)
	if err != nil {
		t.Fatalf("ResolveRepositoryFileSets() error = %v, want nil", err)
	}

	want := []RepoFileSet{
		{
			RepoRoot: mustResolvePath(t, repo),
			Files: []string{
				mustResolvePath(t, filepath.Join(repo, "generated", "keep.py")),
				mustResolvePath(t, filepath.Join(repo, "kept.py")),
			},
		},
	}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ResolveRepositoryFileSets() = %#v, want %#v", got, want)
	}
}

func TestResolveRepositoryFileSetsSkipsSymlinkTargetsOutsideRepoRoot(t *testing.T) {
	t.Parallel()

	root := t.TempDir()
	repo := filepath.Join(root, "repo")
	nestedRepo := filepath.Join(repo, "packages", "nested")

	mustMkdirGit(t, repo)
	mustMkdirGit(t, nestedRepo)

	kept := filepath.Join(repo, "app.py")
	mustWriteFile(t, kept, "print('inside')\n")
	external := filepath.Join(root, "shared.py")
	mustWriteFile(t, external, "print('outside')\n")

	escaped := filepath.Join(repo, "currency.py")
	if err := os.Symlink(external, escaped); err != nil {
		t.Skipf("symlinks unavailable in test environment: %v", err)
	}

	mustWriteFile(t, filepath.Join(nestedRepo, "nested.py"), "print('nested')\n")

	got, err := ResolveRepositoryFileSets(
		repo,
		func(path string) bool {
			return filepath.Ext(path) == ".py"
		},
		Options{
			IgnoredDirs:    []string{".git"},
			IgnoreHidden:   false,
			HonorGitignore: false,
		},
	)
	if err != nil {
		t.Fatalf("ResolveRepositoryFileSets() error = %v, want nil", err)
	}

	want := []RepoFileSet{
		{
			RepoRoot: mustResolvePath(t, repo),
			Files: []string{
				mustResolvePath(t, kept),
			},
		},
		{
			RepoRoot: mustResolvePath(t, nestedRepo),
			Files: []string{
				mustResolvePath(t, filepath.Join(nestedRepo, "nested.py")),
			},
		},
	}

	if !reflect.DeepEqual(got, want) {
		t.Fatalf("ResolveRepositoryFileSets() = %#v, want %#v", got, want)
	}
}

func mustMkdirGit(t *testing.T, dir string) {
	t.Helper()

	if err := os.MkdirAll(filepath.Join(dir, ".git"), 0o755); err != nil {
		t.Fatalf("mkdir .git for %q: %v", dir, err)
	}
}

func mustWriteFile(t *testing.T, path string, contents string) {
	t.Helper()

	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("mkdir parent for %q: %v", path, err)
	}
	if err := os.WriteFile(path, []byte(contents), 0o644); err != nil {
		t.Fatalf("write file %q: %v", path, err)
	}
}

func mustResolvePath(t *testing.T, path string) string {
	t.Helper()

	resolved, err := filepath.EvalSymlinks(path)
	if err != nil {
		t.Fatalf("resolve path %q: %v", path, err)
	}
	return resolved
}

func supportedPathMatcher(path string) bool {
	switch filepath.Base(path) {
	case "Dockerfile":
		return true
	}
	switch filepath.Ext(path) {
	case ".py", ".yaml":
		return true
	default:
		return false
	}
}
