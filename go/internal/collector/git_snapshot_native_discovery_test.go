package collector

import (
	"context"
	"path/filepath"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestNativeRepositorySnapshotterDefaultDiscoverySkipsDependencyDirs(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()

	// Source file that should be indexed.
	writeCollectorTestFile(t, filepath.Join(repoRoot, "main.py"), "def main(): pass\n")

	// Files inside dependency dirs that should be skipped by default.
	for _, dir := range []string{
		"node_modules", "vendor", "__pycache__", "site-packages",
		".terraform", ".terragrunt-cache", "dist", "build", "Pods",
		"ansible_collections", ".jenkins",
	} {
		writeCollectorTestFile(t, filepath.Join(repoRoot, dir, "dep.py"), "def dep(): pass\n")
	}

	// Files with ignored extensions that should be skipped.
	writeCollectorTestFile(t, filepath.Join(repoRoot, "server.log"), "log line\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "test.out"), "output\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "app.min.js"), "minified\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "style.min.css"), "minified\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "bundle.js.map"), "sourcemap\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "lib.pyc"), "compiled\n")

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v", err)
	}

	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}

	now := time.Date(2026, time.April, 15, 12, 0, 0, 0, time.UTC)
	snapshotter := NativeRepositorySnapshotter{
		Engine: engine,
		Now:    func() time.Time { return now },
	}

	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: resolvedRepoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotOneRepository() error = %v", err)
	}

	// Only main.py should be discovered — all dependency dirs should be pruned.
	if got.FileCount != 1 {
		t.Errorf("FileCount = %d, want 1 (only main.py); dependency dirs were not skipped", got.FileCount)
	}
	for _, entity := range got.ContentEntities {
		if entity.EntityName == "dep" {
			t.Errorf("found entity %q from dependency dir; default ignored dirs not applied", entity.RelativePath)
		}
	}
}
