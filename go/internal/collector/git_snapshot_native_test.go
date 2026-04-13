package collector

import (
	"context"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestNativeRepositorySnapshotterSnapshotsOneRepository(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "app.py")
	writeCollectorTestFile(
		t,
		filePath,
		"def handler():\n    return 1\n\nclass Worker:\n    pass\n",
	)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}
	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}

	now := time.Date(2026, time.April, 13, 12, 0, 0, 0, time.UTC)
	snapshotter := NativeRepositorySnapshotter{
		Engine: engine,
		Now: func() time.Time {
			return now
		},
	}

	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{
			RepoPath:  repoRoot,
			RemoteURL: "https://github.com/example/service",
		},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}

	if got.RepoPath != resolvedRepoRoot {
		t.Fatalf("RepoPath = %q, want %q", got.RepoPath, resolvedRepoRoot)
	}
	if got.RemoteURL != "https://github.com/example/service" {
		t.Fatalf("RemoteURL = %q, want %q", got.RemoteURL, "https://github.com/example/service")
	}
	if got.FileCount != 1 {
		t.Fatalf("FileCount = %d, want 1", got.FileCount)
	}
	if len(got.FileData) != 1 {
		t.Fatalf("len(FileData) = %d, want 1", len(got.FileData))
	}

	parsedFile := got.FileData[0]
	functions, _ := parsedFile["functions"].([]map[string]any)
	classes, _ := parsedFile["classes"].([]map[string]any)
	if uid, _ := functions[0]["uid"].(string); uid == "" {
		t.Fatal("functions[0].uid = empty, want canonical content entity id")
	}
	if uid, _ := classes[0]["uid"].(string); uid == "" {
		t.Fatal("classes[0].uid = empty, want canonical content entity id")
	}

	if len(got.ContentFiles) != 1 {
		t.Fatalf("len(ContentFiles) = %d, want 1", len(got.ContentFiles))
	}
	contentFile := got.ContentFiles[0]
	if contentFile.RelativePath != "app.py" {
		t.Fatalf("ContentFiles[0].RelativePath = %q, want %q", contentFile.RelativePath, "app.py")
	}
	if contentFile.Body != "def handler():\n    return 1\n\nclass Worker:\n    pass\n" {
		t.Fatalf("ContentFiles[0].Body = %q, want source body", contentFile.Body)
	}
	if contentFile.Digest == "" {
		t.Fatal("ContentFiles[0].Digest = empty, want content hash")
	}
	if contentFile.Language != "python" {
		t.Fatalf("ContentFiles[0].Language = %q, want %q", contentFile.Language, "python")
	}

	if len(got.ContentEntities) != 2 {
		t.Fatalf("len(ContentEntities) = %d, want 2", len(got.ContentEntities))
	}
	if got.ContentEntities[0].EntityName != "handler" {
		t.Fatalf("ContentEntities[0].EntityName = %q, want %q", got.ContentEntities[0].EntityName, "handler")
	}
	if got.ContentEntities[0].EntityType != "Function" {
		t.Fatalf("ContentEntities[0].EntityType = %q, want %q", got.ContentEntities[0].EntityType, "Function")
	}
	if got.ContentEntities[0].IndexedAt != now {
		t.Fatalf("ContentEntities[0].IndexedAt = %v, want %v", got.ContentEntities[0].IndexedAt, now)
	}
	if got.ContentEntities[1].EntityName != "Worker" {
		t.Fatalf("ContentEntities[1].EntityName = %q, want %q", got.ContentEntities[1].EntityName, "Worker")
	}
	if got.ContentEntities[1].EntityType != "Class" {
		t.Fatalf("ContentEntities[1].EntityType = %q, want %q", got.ContentEntities[1].EntityType, "Class")
	}
}

func TestNativeRepositorySnapshotterReturnsEmptySnapshotForRepoWithoutSupportedFiles(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(t, filepath.Join(repoRoot, "README.md"), "# hello\n")

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	snapshotter := NativeRepositorySnapshotter{Engine: engine}
	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: repoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}

	if got.FileCount != 0 {
		t.Fatalf("FileCount = %d, want 0", got.FileCount)
	}
	if len(got.FileData) != 0 {
		t.Fatalf("len(FileData) = %d, want 0", len(got.FileData))
	}
	if len(got.ContentFiles) != 0 {
		t.Fatalf("len(ContentFiles) = %d, want 0", len(got.ContentFiles))
	}
	if len(got.ContentEntities) != 0 {
		t.Fatalf("len(ContentEntities) = %d, want 0", len(got.ContentEntities))
	}
}

func TestNativeRepositorySnapshotterIncludesImportsMap(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(
		t,
		filepath.Join(repoRoot, "app.py"),
		"from helpers import Helper\n\ndef handler():\n    return Helper()\n",
	)
	writeCollectorTestFile(
		t,
		filepath.Join(repoRoot, "helpers.py"),
		"class Helper:\n    pass\n",
	)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	snapshotter := NativeRepositorySnapshotter{Engine: engine}
	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: repoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}

	helperPaths, ok := got.ImportsMap["Helper"]
	if !ok {
		t.Fatalf("ImportsMap missing Helper entry: %#v", got.ImportsMap)
	}
	if len(helperPaths) != 1 {
		t.Fatalf("len(ImportsMap[Helper]) = %d, want 1", len(helperPaths))
	}
	if got, want := filepath.Base(helperPaths[0]), "helpers.py"; got != want {
		t.Fatalf("ImportsMap[Helper][0] base = %q, want %q", got, want)
	}

	handlerPaths, ok := got.ImportsMap["handler"]
	if !ok {
		t.Fatalf("ImportsMap missing handler entry: %#v", got.ImportsMap)
	}
	if len(handlerPaths) != 1 {
		t.Fatalf("len(ImportsMap[handler]) = %d, want 1", len(handlerPaths))
	}
	if got, want := filepath.Base(handlerPaths[0]), "app.py"; got != want {
		t.Fatalf("ImportsMap[handler][0] base = %q, want %q", got, want)
	}
}

func TestNativeRepositorySnapshotterPreservesDependencyOwnership(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(
		t,
		filepath.Join(repoRoot, "client.py"),
		"def fetch():\n    return 1\n",
	)

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	snapshotter := NativeRepositorySnapshotter{Engine: engine}
	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{
			RepoPath:     repoRoot,
			IsDependency: true,
			DisplayName:  "requests",
			Language:     "python",
		},
	)
	if err != nil {
		t.Fatalf("SnapshotRepository() error = %v, want nil", err)
	}
	if got.FileCount != 1 {
		t.Fatalf("FileCount = %d, want 1", got.FileCount)
	}

	parsedFile := got.FileData[0]
	if got, want := parsedFile["is_dependency"], true; got != want {
		t.Fatalf("parsed file is_dependency = %#v, want %#v", got, want)
	}
}

func writeCollectorTestFile(t *testing.T, path string, body string) {
	t.Helper()

	if err := os.MkdirAll(filepath.Dir(path), 0o755); err != nil {
		t.Fatalf("MkdirAll(%q) error = %v, want nil", filepath.Dir(path), err)
	}
	if err := os.WriteFile(path, []byte(body), 0o644); err != nil {
		t.Fatalf("WriteFile(%q) error = %v, want nil", path, err)
	}
}
