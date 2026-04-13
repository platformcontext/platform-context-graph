package collector

import (
	"context"
	"errors"
	"testing"
	"time"
)

func TestGitSourceNextBuildsCollectedGenerationFromSelectionAndPerRepoSnapshots(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	firstRepoPath := t.TempDir()
	secondRepoPath := t.TempDir()
	selector := &stubRepositorySelector{
		batches: []SelectionBatch{{
			ObservedAt: observedAt,
			Repositories: []SelectedRepository{
				{
					RepoPath:  firstRepoPath,
					RemoteURL: "https://github.com/example/service-one",
				},
				{
					RepoPath:  secondRepoPath,
					RemoteURL: "https://github.com/example/service-two",
				},
			},
		}},
	}
	snapshotter := &stubRepositorySnapshotter{
		snapshots: map[string]RepositorySnapshot{
			firstRepoPath: {
				RepoPath:  firstRepoPath,
				RemoteURL: "https://github.com/example/service",
				FileCount: 1,
				ImportsMap: map[string][]string{
					"Worker": {firstRepoPath + "/app.py"},
				},
				FileData: []map[string]any{{
					"path": firstRepoPath + "/app.py",
					"lang": "python",
					"functions": []any{
						map[string]any{
							"name":        "handler",
							"line_number": 1,
							"uid":         "content-entity:e_fn123456789",
						},
					},
				}},
				ContentFiles: []ContentFileSnapshot{{
					RelativePath: "app.py",
					Body:         "def handler():\n    return 1\n",
					Digest:       "digest-1",
					Language:     "python",
				}},
				ContentEntities: []ContentEntitySnapshot{{
					EntityID:     "content-entity:e_fn123456789",
					RelativePath: "app.py",
					EntityType:   "Function",
					EntityName:   "handler",
					StartLine:    1,
					EndLine:      2,
					Language:     "python",
					SourceCache:  "def handler():\n    return 1\n",
					IndexedAt:    observedAt,
					Metadata: map[string]any{
						"docstring":  "Handles requests.",
						"decorators": []string{"@cached"},
					},
				}},
			},
			secondRepoPath: {
				RepoPath:  secondRepoPath,
				RemoteURL: "https://github.com/example/service-two",
				FileCount: 0,
			},
		},
	}

	source := &GitSource{
		Component:   "collector-git",
		Selector:    selector,
		Snapshotter: snapshotter,
	}

	firstCollected, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next() ok = false, want true")
	}
	if got, want := firstCollected.Scope.SourceSystem, "git"; got != want {
		t.Fatalf("Scope.SourceSystem = %q, want %q", got, want)
	}
	if got, want := string(firstCollected.Scope.ScopeKind), "repository"; got != want {
		t.Fatalf("Scope.ScopeKind = %q, want %q", got, want)
	}
	if got, want := string(firstCollected.Generation.TriggerKind), "snapshot"; got != want {
		t.Fatalf("Generation.TriggerKind = %q, want %q", got, want)
	}
	if got, want := len(firstCollected.Facts), 5; got != want {
		t.Fatalf("len(Facts) = %d, want %d", got, want)
	}

	wantKinds := []string{
		"repository",
		"file",
		"content",
		"content_entity",
		"shared_followup",
	}
	for i, want := range wantKinds {
		if got := firstCollected.Facts[i].FactKind; got != want {
			t.Fatalf("Facts[%d].FactKind = %q, want %q", i, got, want)
		}
	}

	repositoryFact := firstCollected.Facts[0]
	importsMap, ok := repositoryFact.Payload["imports_map"].(map[string][]string)
	if !ok {
		t.Fatalf("repository fact imports_map = %#v, want map[string][]string", repositoryFact.Payload["imports_map"])
	}
	if got, want := importsMap["Worker"][0], firstRepoPath+"/app.py"; got != want {
		t.Fatalf("repository fact imports_map Worker path = %q, want %q", got, want)
	}

	fileFact := firstCollected.Facts[1]
	if got, want := fileFact.Payload["relative_path"], "app.py"; got != want {
		t.Fatalf("file fact relative_path = %#v, want %#v", got, want)
	}
	if _, ok := fileFact.Payload["parsed_file_data"]; !ok {
		t.Fatal("file fact parsed_file_data missing, want present")
	}

	entityFact := firstCollected.Facts[3]
	if got, want := entityFact.Payload["entity_id"], "content-entity:e_fn123456789"; got != want {
		t.Fatalf("entity fact entity_id = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["entity_type"], "Function"; got != want {
		t.Fatalf("entity fact entity_type = %#v, want %#v", got, want)
	}
	if got, want := entityFact.Payload["source_cache"], "def handler():\n    return 1\n"; got != want {
		t.Fatalf("entity fact source_cache = %#v, want %#v", got, want)
	}
	entityMetadata, ok := entityFact.Payload["entity_metadata"].(map[string]any)
	if !ok {
		t.Fatalf("entity fact entity_metadata = %T, want map[string]any", entityFact.Payload["entity_metadata"])
	}
	if got, want := entityMetadata["docstring"], "Handles requests."; got != want {
		t.Fatalf("entity fact entity_metadata[docstring] = %#v, want %#v", got, want)
	}

	secondCollected, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next(second) error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next(second) ok = false, want true")
	}
	if got, want := secondCollected.Scope.Metadata["repo_name"], filepathBase(secondRepoPath); got != want {
		t.Fatalf("second scope repo_name = %q, want %q", got, want)
	}
	if got, want := len(secondCollected.Facts), 2; got != want {
		t.Fatalf("len(second facts) = %d, want %d", got, want)
	}
	if got, want := selector.calls, 1; got != want {
		t.Fatalf("selector calls = %d, want %d", got, want)
	}
	if got, want := snapshotter.calls, []string{firstRepoPath, secondRepoPath}; !equalStrings(got, want) {
		t.Fatalf("snapshotter calls = %v, want %v", got, want)
	}
}

func TestGitSourceNextReturnsEmptyWhenSelectionBatchIsEmpty(t *testing.T) {
	t.Parallel()

	source := &GitSource{
		Component: "collector-git",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt:   time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC),
				Repositories: nil,
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{snapshots: map[string]RepositorySnapshot{}},
	}

	_, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if ok {
		t.Fatal("Next() ok = true, want false")
	}
}

func TestGitSourceNextEmitsDependencyOwnershipForDependencyRepositories(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	repoPath := t.TempDir()
	source := &GitSource{
		Component: "bootstrap-index",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{
						RepoPath:     repoPath,
						IsDependency: true,
						DisplayName:  "@scope/service-lib",
						Language:     "typescript",
					},
				},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				repoPath: {
					RepoPath:  repoPath,
					FileCount: 1,
					FileData: []map[string]any{{
						"path":          repoPath + "/index.ts",
						"lang":          "typescript",
						"is_dependency": true,
						"functions":     []any{},
						"classes":       []any{},
						"variables":     []any{},
						"imports":       []any{},
					}},
				},
			},
		},
	}

	collected, ok, err := source.Next(context.Background())
	if err != nil {
		t.Fatalf("Next() error = %v, want nil", err)
	}
	if !ok {
		t.Fatal("Next() ok = false, want true")
	}
	if got, want := collected.Scope.Metadata["repo_name"], "@scope/service-lib"; got != want {
		t.Fatalf("scope repo_name = %q, want %q", got, want)
	}
	if got, want := collected.Facts[0].Payload["is_dependency"], true; got != want {
		t.Fatalf("repository fact is_dependency = %#v, want %#v", got, want)
	}
	if got, want := collected.Facts[1].Payload["is_dependency"], true; got != want {
		t.Fatalf("file fact is_dependency = %#v, want %#v", got, want)
	}
}

func TestGitSourceNextDoesNotBufferPartialResultsWhenSnapshottingFails(t *testing.T) {
	t.Parallel()

	observedAt := time.Date(2026, time.April, 12, 15, 30, 0, 0, time.UTC)
	firstRepoPath := t.TempDir()
	secondRepoPath := t.TempDir()
	source := &GitSource{
		Component: "collector-git",
		Selector: &stubRepositorySelector{
			batches: []SelectionBatch{{
				ObservedAt: observedAt,
				Repositories: []SelectedRepository{
					{RepoPath: firstRepoPath, RemoteURL: "https://github.com/example/one"},
					{RepoPath: secondRepoPath, RemoteURL: "https://github.com/example/two"},
				},
			}},
		},
		Snapshotter: &stubRepositorySnapshotter{
			snapshots: map[string]RepositorySnapshot{
				firstRepoPath: {RepoPath: firstRepoPath, FileCount: 1},
			},
			errForRepoPath: map[string]error{
				secondRepoPath: errors.New("boom"),
			},
		},
	}

	_, ok, err := source.Next(context.Background())
	if err == nil {
		t.Fatal("Next() error = nil, want non-nil")
	}
	if ok {
		t.Fatal("Next() ok = true, want false")
	}
	if len(source.pending) != 0 {
		t.Fatalf("pending buffered generations = %d, want 0", len(source.pending))
	}
}

type stubRepositorySelector struct {
	batches []SelectionBatch
	calls   int
}

func (s *stubRepositorySelector) SelectRepositories(context.Context) (SelectionBatch, error) {
	if s.calls >= len(s.batches) {
		s.calls++
		return SelectionBatch{}, nil
	}

	batch := s.batches[s.calls]
	s.calls++
	return batch, nil
}

type stubRepositorySnapshotter struct {
	snapshots      map[string]RepositorySnapshot
	errForRepoPath map[string]error
	calls          []string
}

func (s *stubRepositorySnapshotter) SnapshotRepository(
	_ context.Context,
	repository SelectedRepository,
) (RepositorySnapshot, error) {
	s.calls = append(s.calls, repository.RepoPath)
	if err := s.errForRepoPath[repository.RepoPath]; err != nil {
		return RepositorySnapshot{}, err
	}
	snapshot, ok := s.snapshots[repository.RepoPath]
	if !ok {
		return RepositorySnapshot{}, nil
	}
	return snapshot, nil
}

func equalStrings(got, want []string) bool {
	if len(got) != len(want) {
		return false
	}
	for i := range got {
		if got[i] != want[i] {
			return false
		}
	}
	return true
}

func filepathBase(path string) string {
	lastSlash := -1
	for i := range path {
		if path[i] == '/' {
			lastSlash = i
		}
	}
	if lastSlash < 0 {
		return path
	}
	return path[lastSlash+1:]
}
